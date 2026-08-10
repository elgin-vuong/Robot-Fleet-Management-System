from backend.simulator.robot import Robot


class Fleet:
    def __init__(self, count=5):
        self.robots = {
            f"R{i:03}": Robot(f"R{i:03}")
            for i in range(1, count + 1)
        }

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

        if robot is None:
            return False

        if command == "START":
            robot.start()

        elif command == "STOP":
            robot.stop()

        else:
            return False

        return True
