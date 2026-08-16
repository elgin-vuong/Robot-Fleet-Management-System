from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.database import SessionLocal, get_db
from backend.app.models.command import Command
from backend.app.models.robot import Robot
from backend.app.schemas.robot import RobotResponse, RobotCommand


router = APIRouter(prefix="/robots", tags=["robots"])

ROBOT_COUNT = 5
COMMAND_STATUS = {"START": "MOVING", "STOP": "STOPPED"}


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
def get_robots(db: Session = Depends(get_db)):
    return db.query(Robot).all()


@router.get("/{robot_id}", response_model=RobotResponse)
def get_robot(robot_id: str, db: Session = Depends(get_db)):
    robot = db.get(Robot, robot_id)

    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")

    return robot

@router.post("/{robot_id}/command")
def send_command(robot_id: str, command: RobotCommand, db: Session = Depends(get_db)):
    robot = db.get(Robot, robot_id)

    if robot is None or command.command not in COMMAND_STATUS:
        raise HTTPException(status_code=404, detail="Invalid command or robot")

    robot.status = COMMAND_STATUS[command.command]
    db.add(Command(robot_id=robot_id, command=command.command))
    db.commit()

    return {
        "robot_id": robot_id,
        "command": command.command,
    }