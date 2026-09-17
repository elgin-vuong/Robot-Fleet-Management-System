from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

VALID_SEVERITIES = ("low", "medium", "high", "critical")

class IncidentCreateRequest(BaseModel):
    robot_id: str = Field(min_length=1, max_length=32)
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1, max_length=10_000)
    severity: str = Field(pattern="^(" + "|".join(VALID_SEVERITIES) + ")$")

class IncidentResolveRequest(BaseModel):
    resolution_notes: str | None = Field(default=None, max_length=10_000)

class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    robot_id: str
    title: str
    description: str
    severity: str
    status: str
    created_by: int
    created_at: datetime
    resolved_at: datetime | None
    resolution_notes: str | None
