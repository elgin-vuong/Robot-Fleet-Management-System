from fastapi import APIRouter, HTTPException
from backend.simulator.fleet import Fleet
from backend.app.schemas.robot import RobotResponse, RobotCommand


router = APIRouter(prefix="/robots", tags=["robots"])


fleet = Fleet(5)


@router.get("", response_model=list[RobotResponse])
def get_robots():
    return fleet.get_all_robots()


@router.get("/{robot_id}", response_model=RobotResponse)
def get_robot(robot_id: str):
    robot = fleet.get_robot(robot_id)

    if robot is None:
        raise HTTPException(status_code=404, detail="Robot not found")

    return robot

@router.post("/{robot_id}/command")
def send_command(robot_id: str, command: RobotCommand):

    success = fleet.send_command(robot_id, command.command)

    if not success:
        raise HTTPException(status_code=404, detail="Invalid command or robot")

    return {
        "robot_id": robot_id,
        "command": command.command,
        # "status": "accepted",
    }