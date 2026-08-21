import random

FAILURE_STATUSES = {
    "ERROR",
    "NETWORK_ERROR",
    "MOTOR_ERROR",
    "OBSTACLE_DETECTED",
    "OFFLINE",
}

LOW_BATTERY_THRESHOLD = 20.0
OFFLINE_BATTERY_THRESHOLD = 0.0
OVERHEATING_THRESHOLD = 70.0

FAILURE_PROBABILITY = 0.01

POSITION_MIN = -100.0
POSITION_MAX = 100.0


class Robot:
    def __init__(self, robot_id):
        self.id = robot_id
        self.battery = 100.0
        self.temperature = 35.0
        self.x = 0.0
        self.y = 0.0
        self.speed = 0.0
        self.status = "IDLE"

    def start(self):
        if self.status in FAILURE_STATUSES:
            return

        self.status = "MOVING"
        self.speed = 1.0

    def stop(self):
        if self.status in FAILURE_STATUSES:
            return

        self.status = "STOPPED"
        self.speed = 0.0

    def charge(self):
        if self.status in FAILURE_STATUSES:
            return

        self.status = "CHARGING"
        self.speed = 0.0

    def reset(self):
        """Clear a failure/offline condition and return the robot to IDLE."""
        self.status = "IDLE"
        self.speed = 0.0

    def update(self):
        # Failure states are terminal until an explicit RESET command.
        if self.status in FAILURE_STATUSES:
            return

        if self.status == "MOVING":
            self._move()
            self._drain_battery(0.2)
            self._heat(0.5)
            self._maybe_fail()
        elif self.status == "CHARGING":
            self._charge_battery(1.0)
            self._cool(0.3)
        elif self.status in ("IDLE", "STOPPED", "LOW_BATTERY"):
            self._drain_battery(0.01)
            self._cool(0.1)
        elif self.status == "OVERHEATING":
            self._cool(0.5)

        self._apply_thresholds()

    def _move(self):
        self.x += self.speed + random.uniform(-0.5, 0.5)
        self.y += random.uniform(-0.5, 0.5)

        self.x = max(POSITION_MIN, min(POSITION_MAX, self.x))
        self.y = max(POSITION_MIN, min(POSITION_MAX, self.y))

    def _drain_battery(self, amount):
        self.battery -= amount
        self.battery = max(0.0, self.battery)

    def _charge_battery(self, amount):
        self.battery += amount
        self.battery = min(100.0, self.battery)

    def _heat(self, amount):
        self.temperature += amount

    def _cool(self, amount):
        self.temperature = max(20.0, self.temperature - amount)

    def _maybe_fail(self):
        if random.random() < FAILURE_PROBABILITY:
            self.status = random.choice(
                ["ERROR", "NETWORK_ERROR", "MOTOR_ERROR", "OBSTACLE_DETECTED"]
            )
            self.speed = 0.0

    def _apply_thresholds(self):
        if self.battery <= OFFLINE_BATTERY_THRESHOLD:
            self.status = "OFFLINE"
            self.speed = 0.0
        elif self.temperature > OVERHEATING_THRESHOLD:
            self.status = "OVERHEATING"
            self.speed = 0.0
        elif self.battery < LOW_BATTERY_THRESHOLD and self.status == "MOVING":
            self.status = "LOW_BATTERY"
            self.speed = 0.0
        elif self.status in ("OVERHEATING", "LOW_BATTERY"):
            self.status = "IDLE"

    def get_telemetry(self):
        return {
            "id": self.id,
            "battery": round(self.battery, 2),
            "temperature": round(self.temperature, 2),
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "speed": self.speed,
            "status": self.status,
        }
