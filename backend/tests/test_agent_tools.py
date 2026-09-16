import pytest
from pydantic import ValidationError

from backend.app.agent.exceptions import RobotNotFoundError, ToolValidationError
from backend.app.agent.tools import (
    ToolContext,
    get_fleet_summary,
    get_recent_incidents,
    get_recent_telemetry,
    get_robot_logs,
    get_robot_status,
    send_robot_command,
)
from backend.app.database import SessionLocal
from backend.app.models.command import Command
from backend.app.models.robot import Robot
from backend.app.models.telemetry import Telemetry
from backend.app.models.user import User


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def operator_ctx(db):
    operator = db.query(User).filter(User.username == "operator1").first()
    return ToolContext(db=db, current_user=operator)


def test_get_fleet_summary_counts_seeded_robots(operator_ctx):
    summary = get_fleet_summary(operator_ctx)

    assert summary.total_robots >= 5
    assert summary.average_battery is not None
    # Every robot is counted into exactly one bucket.
    assert (
        summary.active + summary.idle + summary.charging + summary.needs_attention + summary.offline
        == summary.total_robots
    )


def test_get_robot_status_known_robot(operator_ctx):
    status = get_robot_status(operator_ctx, "R001")

    assert status.robot_id == "R001"
    assert status.health in ("good", "attention", "offline")
    assert 0.0 <= status.battery <= 100.0


def test_get_robot_status_unknown_robot_raises(operator_ctx):
    with pytest.raises(RobotNotFoundError):
        get_robot_status(operator_ctx, "R999")


def test_get_recent_telemetry_rejects_limit_too_high(operator_ctx):
    with pytest.raises(ValidationError):
        get_recent_telemetry(operator_ctx, "R001", limit=101)


def test_get_recent_telemetry_rejects_limit_too_low(operator_ctx):
    with pytest.raises(ValidationError):
        get_recent_telemetry(operator_ctx, "R001", limit=0)


def test_get_recent_telemetry_respects_limit(db, operator_ctx):
    db.query(Telemetry).filter(Telemetry.robot_id == "R004").delete()
    for i in range(5):
        db.add(Telemetry(robot_id="R004", battery=100.0 - i, temperature=30.0, x=0.0, y=0.0))
    db.commit()

    result = get_recent_telemetry(operator_ctx, "R004", limit=2)

    assert result.robot_id == "R004"
    assert len(result.readings) == 2


def test_get_recent_telemetry_unknown_robot_raises(operator_ctx):
    with pytest.raises(RobotNotFoundError):
        get_recent_telemetry(operator_ctx, "R999")


def test_get_recent_incidents_is_an_empty_stub(operator_ctx):
    result = get_recent_incidents(operator_ctx, "R001")

    assert result.incidents == []
    assert "not implemented" in result.note.lower()


def test_get_recent_incidents_unknown_robot_raises(operator_ctx):
    with pytest.raises(RobotNotFoundError):
        get_recent_incidents(operator_ctx, "R999")


def test_get_robot_logs_reflects_command_table(db, operator_ctx):
    db.query(Command).filter(Command.robot_id == "R005").delete()
    db.add(Command(robot_id="R005", command="START"))
    db.add(Command(robot_id="R005", command="STOP"))
    db.commit()

    result = get_robot_logs(operator_ctx, "R005", limit=10)

    assert result.robot_id == "R005"
    assert len(result.logs) == 2
    assert {entry.command for entry in result.logs} == {"START", "STOP"}


def test_get_robot_logs_unknown_robot_raises(operator_ctx):
    with pytest.raises(RobotNotFoundError):
        get_robot_logs(operator_ctx, "R999")


def test_send_robot_command_rejects_unsupported_command(db, operator_ctx):
    with pytest.raises(ToolValidationError):
        send_robot_command(operator_ctx, "R001", "FLY")


def test_send_robot_command_rejects_unknown_robot(operator_ctx):
    with pytest.raises(RobotNotFoundError):
        send_robot_command(operator_ctx, "R999", "START")


def test_send_robot_command_executes_via_existing_command_service(db, operator_ctx):
    result = send_robot_command(operator_ctx, "R002", "STOP")

    assert result.robot_id == "R002"
    assert result.new_status == "STOPPED"

    # Proves this went through the real Robot row, not a parallel state store.
    robot = db.get(Robot, "R002")
    assert robot.status == "STOPPED"
