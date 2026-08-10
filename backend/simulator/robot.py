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
        self.status = "MOVING"
        self.speed = 1.0

    def stop(self):
        self.status = "STOPPED"
        self.speed = 0.0

    def update(self):
        if self.status == "MOVING":
            self.x += self.speed
            self.battery -= 0.2
            self.temperature += 0.05

    def get_telemetry(self):
        return {
            "id": self.id,
            "battery": self.battery,
            "temperature": self.temperature,
            "x": self.x,
            "y": self.y,
            "speed": self.speed,
            "status": self.status,
        }
