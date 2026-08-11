from fastapi import APIRouter, HTTPException

from backend.app.schemas.robot import RobotResponse, RobotCommand


router = APIRouter(prefix="/robots", tags=["robots"])


robots = [
    {
        "id": "R001",
        "battery": 92.0,
        "temperature": 36.2,
        "x": 4.2,
        "y": 7.1,
        "speed": 1.3,
        "status": "MOVING",
    },
    {
        "id": "R002",
        "battery": 87.0,
        "temperature": 35.8,
        "x": 9.0,
        "y": 2.5,
        "speed": 0.0,
        "status": "IDLE",
    },
]


@router.get("", response_model=list[RobotResponse])
def get_robots():
    return robots


@router.get("/{robot_id}", response_model=RobotResponse)
def get_robot(robot_id: str):
    for robot in robots:
        if robot["id"] == robot_id:
            return robot

    raise HTTPException(status_code=404, detail="Robot not found")

@router.post("/{robot_id}/command")
def send_command(robot_id: str, command: RobotCommand):
    for robot in robots:
        if robot["id"] == robot_id:

            if command.command == "STOP":
                robot["speed"] = 0.0
                robot["status"] = "STOPPED"
            elif command.command == "START":
                robot["speed"] = 1.0
                robot["status"] = "MOVING"
            else:
                raise HTTPException(status_code=400, detail="Invalid command")

            return {
                "robot_id": robot_id,
                "command": command.command,
                "status": "accepted",
            }

    raise HTTPException(status_code=404, detail="Robot not found")