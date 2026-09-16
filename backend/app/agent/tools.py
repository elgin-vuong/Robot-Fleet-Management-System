"""Controlled tool implementations the agent may call.

Every tool here is a thin, validated wrapper around the application's
existing services — the SQLAlchemy models, the Redis cache, and (for the
one write tool) the existing command service in backend/app/routes/robots.py.
No tool talks to Postgres/Redis/Kafka in a way the rest of the app doesn't
already do, and the write tool never bypasses backend.app.routes.robots's
`execute_robot_command`, which is the single real implementation of "how a
command gets applied" shared with the HTTP endpoint.

Read tools vs. write tools are tracked in TOOL_CLASSIFICATION and enforced
by the orchestrator (agent.py) — a tool function here does not know or care
whether the caller was allowed to invoke it; that check happens before a
tool function is ever called.
"""

import json
import logging
from dataclasses import dataclass
from typing import Callable, Literal

from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.app.agent.exceptions import RobotNotFoundError, ToolNotFoundError, ToolValidationError
from backend.app.agent.schemas import (
    FleetSummaryResult,
    IncidentsResult,
    LimitedRobotArgs,
    MAX_LIMIT,
    RecentTelemetryResult,
    RobotIdArgs,
    RobotLogEntry,
    RobotLogsResult,
    RobotStatusResult,
    SendCommandResult,
    SendRobotCommandArgs,
    TelemetryReading,
)
from backend.app.cache import redis_client
from backend.app.models.command import Command
from backend.app.models.robot import Robot
from backend.app.models.telemetry import Telemetry
from backend.app.models.user import User
from backend.app.routes.robots import COMMAND_STATUS, _robot_cache_key, execute_robot_command

logger = logging.getLogger("backend.app.agent")

ToolClassification = Literal["read", "write"]

# Bucketing of the simulator's status vocabulary for fleet-level summaries.
# This is presentation logic for the agent only — it does not change how
# statuses are stored or interpreted anywhere else in the application.
ACTIVE_STATUSES = {"MOVING"}
CHARGING_STATUSES = {"CHARGING"}
ATTENTION_STATUSES = {
    "LOW_BATTERY",
    "OVERHEATING",
    "ERROR",
    "NETWORK_ERROR",
    "MOTOR_ERROR",
    "OBSTACLE_DETECTED",
}
OFFLINE_STATUSES = {"OFFLINE"}


@dataclass
class ToolContext:
    """Everything a tool needs, threaded in by the orchestrator per-request."""

    db: Session
    current_user: User


def _latest_telemetry(db: Session, robot_id: str) -> Telemetry | None:
    return (
        db.query(Telemetry)
        .filter(Telemetry.robot_id == robot_id)
        .order_by(desc(Telemetry.timestamp), desc(Telemetry.id))
        .first()
    )


# ---------------------------------------------------------------------------
# READ tools
# ---------------------------------------------------------------------------


def get_fleet_summary(ctx: ToolContext) -> FleetSummaryResult:
    robots = ctx.db.query(Robot).all()

    active = idle = charging = attention = offline = 0
    battery_total = 0.0

    for robot in robots:
        battery_total += robot.battery

        if robot.status in ACTIVE_STATUSES:
            active += 1
        elif robot.status in CHARGING_STATUSES:
            charging += 1
        elif robot.status in ATTENTION_STATUSES:
            attention += 1
        elif robot.status in OFFLINE_STATUSES:
            offline += 1
        else:
            # IDLE, STOPPED, or any status we don't specifically recognize.
            idle += 1

    average_battery = round(battery_total / len(robots), 1) if robots else None

    return FleetSummaryResult(
        total_robots=len(robots),
        active=active,
        idle=idle,
        charging=charging,
        needs_attention=attention,
        offline=offline,
        average_battery=average_battery,
    )


def get_robot_status(ctx: ToolContext, robot_id: str) -> RobotStatusResult:
    args = RobotIdArgs(robot_id=robot_id)

    cached = redis_client.get(_robot_cache_key(args.robot_id))
    if cached is not None:
        robot_data = json.loads(cached)
    else:
        robot = ctx.db.get(Robot, args.robot_id)
        if robot is None:
            raise RobotNotFoundError(args.robot_id)
        robot_data = {"id": robot.id, "status": robot.status, "battery": robot.battery}

    latest = _latest_telemetry(ctx.db, args.robot_id)

    status = robot_data["status"]
    if status in OFFLINE_STATUSES:
        health: Literal["good", "attention", "offline"] = "offline"
        issue = status
    elif status in ATTENTION_STATUSES:
        health = "attention"
        issue = status
    else:
        health = "good"
        issue = None

    return RobotStatusResult(
        robot_id=args.robot_id,
        status=status,
        health=health,
        issue=issue,
        battery=robot_data["battery"],
        temperature=latest.temperature if latest else None,
        x=latest.x if latest else None,
        y=latest.y if latest else None,
        # Not persisted anywhere the agent can read: the telemetry_consumer
        # only writes battery/temperature/x/y to Postgres, so live speed is
        # only ever visible over the WebSocket feed, never here. Reported as
        # unknown rather than guessed.
        speed=None,
        last_seen=latest.timestamp if latest else None,
    )


def get_recent_telemetry(ctx: ToolContext, robot_id: str, limit: int = 20) -> RecentTelemetryResult:
    args = LimitedRobotArgs(robot_id=robot_id, limit=limit)

    if ctx.db.get(Robot, args.robot_id) is None:
        raise RobotNotFoundError(args.robot_id)

    rows = (
        ctx.db.query(Telemetry)
        .filter(Telemetry.robot_id == args.robot_id)
        .order_by(desc(Telemetry.timestamp), desc(Telemetry.id))
        .limit(args.limit)
        .all()
    )

    return RecentTelemetryResult(
        robot_id=args.robot_id,
        readings=[TelemetryReading.model_validate(r) for r in rows],
    )


def get_recent_incidents(ctx: ToolContext, robot_id: str, limit: int = 10) -> IncidentsResult:
    """Stub: this codebase has no Incident model yet.

    Kept as a real tool (rather than omitted) so the calling contract is
    stable — a future incident-tracking feature can fill this in without
    changing the agent orchestration, the LLM-facing schema, or any caller.
    """
    args = LimitedRobotArgs(robot_id=robot_id, limit=limit)

    if ctx.db.get(Robot, args.robot_id) is None:
        raise RobotNotFoundError(args.robot_id)

    return IncidentsResult(
        robot_id=args.robot_id,
        incidents=[],
        note="Incident tracking is not implemented in this system yet.",
    )


def get_robot_logs(ctx: ToolContext, robot_id: str, limit: int = 20) -> RobotLogsResult:
    """Recent commands issued to this robot — the closest thing this
    codebase has to an event log for a robot (backend.app.models.command.Command).
    """
    args = LimitedRobotArgs(robot_id=robot_id, limit=limit)

    if ctx.db.get(Robot, args.robot_id) is None:
        raise RobotNotFoundError(args.robot_id)

    rows = (
        ctx.db.query(Command)
        .filter(Command.robot_id == args.robot_id)
        .order_by(desc(Command.created_at), desc(Command.id))
        .limit(args.limit)
        .all()
    )

    return RobotLogsResult(
        robot_id=args.robot_id,
        logs=[RobotLogEntry(command=r.command, created_at=r.created_at) for r in rows],
    )


# ---------------------------------------------------------------------------
# WRITE tools
# ---------------------------------------------------------------------------


def send_robot_command(ctx: ToolContext, robot_id: str, command: str) -> SendCommandResult:
    """Apply a command to a robot.

    This is only ever invoked from POST /agent/confirm after the
    confirmation flow has verified user identity, ownership, expiration,
    and role — never directly from the LLM tool-call loop. It calls the
    exact same backend.app.routes.robots.execute_robot_command used by the
    real HTTP command endpoint, so this is not a second command
    implementation.
    """
    args = SendRobotCommandArgs(robot_id=robot_id, command=command)

    if args.command not in COMMAND_STATUS:
        raise ToolValidationError(
            f"Unsupported command '{args.command}'. Supported commands: {sorted(COMMAND_STATUS)}."
        )

    try:
        robot = execute_robot_command(ctx.db, args.robot_id, args.command)
    except ValueError as exc:
        raise RobotNotFoundError(args.robot_id) from exc

    logger.info(
        "agent.command.executed",
        extra={"user_id": ctx.current_user.id, "robot_id": args.robot_id, "command": args.command},
    )

    return SendCommandResult(robot_id=args.robot_id, command=args.command, new_status=robot.status)


# ---------------------------------------------------------------------------
# Registry + LLM-facing tool schema
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    name: str
    classification: ToolClassification
    func: Callable[..., object]
    description: str
    input_schema: dict


TOOLS: dict[str, ToolSpec] = {
    "get_fleet_summary": ToolSpec(
        name="get_fleet_summary",
        classification="read",
        func=get_fleet_summary,
        description=(
            "Get an aggregate summary of the whole robot fleet: total robots, how many are "
            "active/idle/charging/offline, how many need attention, and the average battery level."
        ),
        input_schema={"type": "object", "properties": {}, "required": []},
    ),
    "get_robot_status": ToolSpec(
        name="get_robot_status",
        classification="read",
        func=get_robot_status,
        description="Get the current status of one robot: state, health, battery, temperature, position, and when it was last seen.",
        input_schema={
            "type": "object",
            "properties": {"robot_id": {"type": "string", "description": "e.g. 'R001'"}},
            "required": ["robot_id"],
        },
    ),
    "get_recent_telemetry": ToolSpec(
        name="get_recent_telemetry",
        classification="read",
        func=get_recent_telemetry,
        description="Get recent historical telemetry readings (battery, temperature, position, timestamp) for one robot.",
        input_schema={
            "type": "object",
            "properties": {
                "robot_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": 20},
            },
            "required": ["robot_id"],
        },
    ),
    "get_recent_incidents": ToolSpec(
        name="get_recent_incidents",
        classification="read",
        func=get_recent_incidents,
        description="Get recent incidents recorded for one robot, if incident tracking is available.",
        input_schema={
            "type": "object",
            "properties": {
                "robot_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": 10},
            },
            "required": ["robot_id"],
        },
    ),
    "get_robot_logs": ToolSpec(
        name="get_robot_logs",
        classification="read",
        func=get_robot_logs,
        description="Get the recent command history (audit log) for one robot.",
        input_schema={
            "type": "object",
            "properties": {
                "robot_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT, "default": 20},
            },
            "required": ["robot_id"],
        },
    ),
    "send_robot_command": ToolSpec(
        name="send_robot_command",
        classification="write",
        func=send_robot_command,
        description=(
            "Send an operational command to a robot (e.g. START, STOP). This is a WRITE action: "
            "it will never execute immediately. Calling this tool always produces a pending "
            "confirmation that a human must explicitly approve before anything happens."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "robot_id": {"type": "string"},
                "command": {"type": "string", "description": "One of the supported robot commands, e.g. START or STOP"},
            },
            "required": ["robot_id", "command"],
        },
    ),
}


def get_tool(name: str) -> ToolSpec:
    try:
        return TOOLS[name]
    except KeyError:
        raise ToolNotFoundError(f"Unknown tool '{name}'")


def tool_specs_for_llm() -> list[dict]:
    """Anthropic Messages API tool-definition shape."""
    return [
        {"name": spec.name, "description": spec.description, "input_schema": spec.input_schema}
        for spec in TOOLS.values()
    ]
