import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from opentelemetry.trace import Status, StatusCode
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app.auth import ROLE_ADMIN, ROLE_OPERATOR, get_current_user, require_role
from backend.app.cache import CACHE_TTL_SECONDS, redis_client
from backend.app.database import SessionLocal, get_db
from backend.app.models.command import Command
from backend.app.models.robot import Robot
from backend.app.models.telemetry import Telemetry
from backend.app.models.user import User
from backend.app.observability.metrics import (
    robot_commands_failed_total,
    robot_commands_processed_total,
    robot_commands_requested_total,
)
from backend.app.observability.tracing import get_tracer
from backend.app.schemas.robot import RobotResponse, RobotCommand
from backend.app.schemas.telemetry import TelemetryResponse

tracer = get_tracer("backend.app.robots")
logger = logging.getLogger("backend.app.robots")


router = APIRouter(prefix="/robots", tags=["robots"])

ROBOT_COUNT = 5
COMMAND_STATUS = {"START": "MOVING", "STOP": "STOPPED"}
ROBOTS_CACHE_KEY = "robots:all"


def _robot_cache_key(robot_id: str) -> str:
    return f"robot:{robot_id}"


def _seed_robots():
    db = SessionLocal()
    try:
        for i in range(1, ROBOT_COUNT + 1):
            robot_id = f"R{i:03}"

            if db.get(Robot, robot_id) is None:
                db.add(Robot(id=robot_id, status="IDLE", battery=100.0))

        db.commit()
    finally:
        db.close()


_seed_robots()


@router.get("", response_model=list[RobotResponse])
def get_robots(db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    cached = redis_client.get(ROBOTS_CACHE_KEY)

    if cached is not None:
        return json.loads(cached)

    robots = db.query(Robot).all()
    payload = [RobotResponse.model_validate(r).model_dump(mode="json") for r in robots]

    redis_client.set(ROBOTS_CACHE_KEY, json.dumps(payload), ex=CACHE_TTL_SECONDS)

    return payload


@router.get("/{robot_id}", response_model=RobotResponse)
def get_robot(robot_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)):
    cache_key = _robot_cache_key(robot_id)
    cached = redis_client.get(cache_key)

    if cached is not None:
        return json.loads(cached)

    robot = db.get(Robot, robot_id)

    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")

    payload = RobotResponse.model_validate(robot).model_dump(mode="json")
    redis_client.set(cache_key, json.dumps(payload), ex=CACHE_TTL_SECONDS)

    return payload


@router.get("/{robot_id}/telemetry", response_model=list[TelemetryResponse])
def get_robot_telemetry(
    robot_id: str,
    limit: int = 50,
    db: Session = Depends(get_db),
    _user: User = Depends(get_current_user),
):
    if db.get(Robot, robot_id) is None:
        raise HTTPException(status_code=404, detail="Robot not found")

    return (
        db.query(Telemetry)
        .filter(Telemetry.robot_id == robot_id)
        .order_by(desc(Telemetry.timestamp), desc(Telemetry.id))
        .limit(limit)
        .all()
    )


@router.get("/{robot_id}/telemetry/latest", response_model=TelemetryResponse)
def get_robot_telemetry_latest(
    robot_id: str, db: Session = Depends(get_db), _user: User = Depends(get_current_user)
):
    if db.get(Robot, robot_id) is None:
        raise HTTPException(status_code=404, detail="Robot not found")

    latest = (
        db.query(Telemetry)
        .filter(Telemetry.robot_id == robot_id)
        .order_by(desc(Telemetry.timestamp), desc(Telemetry.id))
        .first()
    )

    if latest is None:
        raise HTTPException(status_code=404, detail="No telemetry recorded for this robot")

    return latest


def execute_robot_command(db: Session, robot_id: str, command: str) -> Robot:
    """Validate and apply a command to a robot.

    This is the one place that knows how commands are validated and applied
    to a robot's persisted state. Both the HTTP endpoint below and the AI
    agent's write tool (backend/app/agent/tools.py) call this function
    directly, so there is exactly one command implementation rather than
    two copies that could drift apart. It's also therefore the one place
    that needs command metrics/tracing to cover both call paths.

    Raises ValueError if the robot doesn't exist or the command isn't one
    of the currently-supported values in COMMAND_STATUS.

    `command` is only used as a metric label once validated against the
    small, fixed COMMAND_STATUS set — an arbitrary/invalid string from a
    caller is normalized to "invalid" first so it can never create an
    unbounded label value. `robot_id` deliberately isn't used as a label at
    all (see the cardinality note in backend/app/observability/metrics.py).
    """
    command_label = command if command in COMMAND_STATUS else "invalid"
    robot_commands_requested_total.labels(command=command_label).inc()

    with tracer.start_as_current_span("robot.command.execute") as span:
        span.set_attribute("robot.id", robot_id)
        span.set_attribute("command.type", command)

        robot = db.get(Robot, robot_id)

        if robot is None or command not in COMMAND_STATUS:
            robot_commands_failed_total.labels(command=command_label).inc()
            span.set_status(Status(StatusCode.ERROR, "invalid command or robot"))
            raise ValueError("Invalid command or robot")

        robot.status = COMMAND_STATUS[command]
        db.add(Command(robot_id=robot_id, command=command))
        db.commit()

        redis_client.delete(ROBOTS_CACHE_KEY, _robot_cache_key(robot_id))

        robot_commands_processed_total.labels(command=command_label).inc()
        span.set_attribute("robot.new_status", robot.status)

        return robot


@router.post("/{robot_id}/command")
def send_command(
    robot_id: str,
    command: RobotCommand,
    db: Session = Depends(get_db),
    _user: User = Depends(require_role(ROLE_OPERATOR, ROLE_ADMIN)),
):
    try:
        execute_robot_command(db, robot_id, command.command)
    except ValueError:
        logger.warning(
            "robot.command.rejected",
            extra={"robot_id": robot_id, "command": command.command},
        )
        raise HTTPException(status_code=404, detail="Invalid command or robot")

    logger.info(
        "robot.command.accepted",
        extra={"robot_id": robot_id, "command": command.command},
    )

    return {
        "robot_id": robot_id,
        "command": command.command,
    }
