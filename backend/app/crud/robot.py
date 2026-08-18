from sqlalchemy.orm import Session

from backend.app.models.robot import Robot


def upsert_robot(db: Session, telemetry: dict) -> Robot:
    """Mirror a simulator telemetry snapshot into the robots table.

    The in-memory Fleet remains the source of truth; this just persists
    its latest known state, keyed on the simulator's robot_id.
    """
    robot = db.query(Robot).filter(Robot.robot_id == telemetry["id"]).first()

    if robot is None:
        robot = Robot(robot_id=telemetry["id"])
        db.add(robot)

    robot.battery = telemetry["battery"]
    robot.temperature = telemetry["temperature"]
    robot.x = telemetry["x"]
    robot.y = telemetry["y"]
    robot.speed = telemetry["speed"]
    robot.status = telemetry["status"]

    db.commit()
    db.refresh(robot)

    return robot


def upsert_robots(db: Session, telemetry_list: list[dict]) -> list[Robot]:
    return [upsert_robot(db, telemetry) for telemetry in telemetry_list]


def load_all_states(db: Session) -> dict[str, dict]:
    """Return {robot_id: telemetry dict} for every persisted robot, for
    restoring an in-memory Fleet to its last-known state on startup.
    """
    return {
        robot.robot_id: {
            "battery": robot.battery,
            "temperature": robot.temperature,
            "x": robot.x,
            "y": robot.y,
            "speed": robot.speed,
            "status": robot.status,
        }
        for robot in db.query(Robot).all()
    }
