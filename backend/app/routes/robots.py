from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.simulator.fleet import Fleet
from backend.app.crud.robot import load_all_states, upsert_robot, upsert_robots
from backend.app.database import SessionLocal, get_db
from backend.app.schemas.robot import RobotResponse, RobotCommand


router = APIRouter(prefix="/robots", tags=["robots"])


def _build_fleet() -> Fleet:
    """Restore robots to their last-known persisted state, if any, instead
    of always booting fresh at battery=100/IDLE/(0,0).
    """
    db = SessionLocal()

    try:
        saved_states = load_all_states(db)
    finally:
        db.close()

    return Fleet(5, saved_states=saved_states)


fleet = _build_fleet()


@router.get("", response_model=list[RobotResponse])
def get_robots(db: Session = Depends(get_db)):
    telemetry = fleet.get_all_robots()
    upsert_robots(db, telemetry)

    return telemetry


@router.get("/{robot_id}", response_model=RobotResponse)
def get_robot(robot_id: str, db: Session = Depends(get_db)):
    telemetry = fleet.get_robot(robot_id)

    if telemetry is None:
        raise HTTPException(status_code=404, detail="Robot not found")

    upsert_robot(db, telemetry)

    return telemetry

@router.post("/{robot_id}/command")
def send_command(robot_id: str, command: RobotCommand, db: Session = Depends(get_db)):

    success = fleet.send_command(robot_id, command.command)

    if not success:
        raise HTTPException(status_code=404, detail="Invalid command or robot")

    upsert_robot(db, fleet.get_robot(robot_id))

    return {
        "robot_id": robot_id,
        "command": command.command,
        # "status": "accepted",
    }