from backend.app.database import SessionLocal
from backend.app.kafka import TELEMETRY_TOPIC, get_producer
from backend.app.models.command import Command
from backend.app.models.robot import Robot as RobotRecord
from backend.simulator.robot import Robot

VALID_COMMANDS = ("START", "STOP", "CHARGE", "RESET")


class Fleet:
    def __init__(self, count=5, persist=True, publish=True):
        self.robots = {
            f"R{i:03}": Robot(f"R{i:03}")
            for i in range(1, count + 1)
        }
        self.persist = persist
        self.publish = publish

        if self.persist:
            self._sync_robots_to_db()

    def get_all_robots(self):
        return [
            robot.get_telemetry()
            for robot in self.robots.values()
        ]

    def get_robot(self, robot_id):
        robot = self.robots.get(robot_id)

        if robot is None:
            return None

        return robot.get_telemetry()

    def send_command(self, robot_id, command):
        robot = self.robots.get(robot_id)

        if robot is None or command not in VALID_COMMANDS:
            return False

        if command == "START":
            robot.start()
        elif command == "STOP":
            robot.stop()
        elif command == "CHARGE":
            robot.charge()
        elif command == "RESET":
            robot.reset()

        if self.persist:
            self._record_command(robot_id, command)
            self._save_robot(robot)

        return True

    def update_all(self):
        for robot in self.robots.values():
            robot.update()

            if self.publish:
                self._publish_telemetry(robot)

            if self.persist:
                self._save_robot(robot)

    def _sync_robots_to_db(self):
        db = SessionLocal()
        try:
            for robot in self.robots.values():
                record = db.get(RobotRecord, robot.id)

                if record is None:
                    db.add(
                        RobotRecord(
                            id=robot.id,
                            status=robot.status,
                            battery=robot.battery,
                        )
                    )
                else:
                    record.status = robot.status
                    record.battery = robot.battery

            db.commit()
        finally:
            db.close()

    def _save_robot(self, robot):
        db = SessionLocal()
        try:
            record = db.get(RobotRecord, robot.id)

            if record is None:
                db.add(
                    RobotRecord(
                        id=robot.id,
                        status=robot.status,
                        battery=robot.battery,
                    )
                )
            else:
                record.status = robot.status
                record.battery = robot.battery

            db.commit()
        finally:
            db.close()

    def _record_command(self, robot_id, command):
        db = SessionLocal()
        try:
            db.add(Command(robot_id=robot_id, command=command))
            db.commit()
        finally:
            db.close()

    def _publish_telemetry(self, robot):
        producer = get_producer()
        producer.send(TELEMETRY_TOPIC, key=robot.id, value=robot.get_telemetry())
