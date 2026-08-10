from pydantic import BaseModel

class RobotResponse(BaseModel):
    id: str
    battery: float
    temperature: float
    x: float
    y: float
    speed: float
    status: str

class RobotCommand(BaseModel):
    command: str
