"""Pydantic models for the agent layer.

Split into three groups:
  - API request/response shapes (POST /agent/chat, POST /agent/confirm)
  - tool argument models (validated before any tool ever runs)
  - tool result models (the typed contract each tool returns)
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_LIMIT = 100

# ---------------------------------------------------------------------------
# API request/response shapes
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class ToolCallRecord(BaseModel):
    tool: str
    status: Literal["success", "error"]
    detail: str | None = None


class ChatResponse(BaseModel):
    response: str
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    requires_confirmation: bool = False
    confirmation_id: str | None = None


class ConfirmRequest(BaseModel):
    confirmation_id: str = Field(min_length=1, max_length=64)


class ConfirmResponse(BaseModel):
    response: str
    success: bool
    robot_id: str | None = None
    command: str | None = None


# ---------------------------------------------------------------------------
# Tool argument models
# ---------------------------------------------------------------------------


class RobotIdArgs(BaseModel):
    robot_id: str = Field(min_length=1, max_length=32)


class LimitedRobotArgs(BaseModel):
    robot_id: str = Field(min_length=1, max_length=32)
    limit: int = Field(default=20, ge=1, le=MAX_LIMIT)


class SendRobotCommandArgs(BaseModel):
    robot_id: str = Field(min_length=1, max_length=32)
    command: str = Field(min_length=1, max_length=32)


# ---------------------------------------------------------------------------
# Tool result models
# ---------------------------------------------------------------------------


class FleetSummaryResult(BaseModel):
    total_robots: int
    active: int
    idle: int
    charging: int
    needs_attention: int
    offline: int
    average_battery: float | None


class RobotStatusResult(BaseModel):
    robot_id: str
    status: str
    health: Literal["good", "attention", "offline"]
    issue: str | None
    battery: float
    temperature: float | None
    x: float | None
    y: float | None
    speed: float | None
    last_seen: datetime | None


class TelemetryReading(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    battery: float
    temperature: float
    x: float
    y: float
    timestamp: datetime


class RecentTelemetryResult(BaseModel):
    robot_id: str
    readings: list[TelemetryReading]


class IncidentsResult(BaseModel):
    robot_id: str
    incidents: list[dict] = Field(default_factory=list)
    note: str


class RobotLogEntry(BaseModel):
    command: str
    created_at: datetime


class RobotLogsResult(BaseModel):
    robot_id: str
    logs: list[RobotLogEntry]


class SendCommandResult(BaseModel):
    robot_id: str
    command: str
    new_status: str
