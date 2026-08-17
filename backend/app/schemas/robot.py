from datetime import datetime

from pydantic import BaseModel, ConfigDict

class RobotResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    status: str
    battery: float
    created_at: datetime

class RobotCommand(BaseModel):
    command: str
