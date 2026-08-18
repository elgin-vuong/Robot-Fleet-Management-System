from datetime import datetime

from pydantic import BaseModel, ConfigDict

class TelemetryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    robot_id: str
    battery: float
    temperature: float
    x: float
    y: float
    timestamp: datetime
