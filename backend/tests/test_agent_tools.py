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
    search_documents,
    send_robot_command,
)
from backend.app.database import SessionLocal
from backend.app.models.command import Command
from backend.app.models.document import Document
from backend.app.models.document_chunk import DocumentChunk
from backend.app.models.incident import Incident
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


def test_get_recent_incidents_reflects_incident_table(db, operator_ctx):
    db.query(Incident).filter(Incident.robot_id == "R001").delete()
    operator = db.query(User).filter(User.username == "operator1").first()
    db.add(
        Incident(
            robot_id="R001",
            title="Overheating",
            description="Temp spiked",
            severity="high",
            status="open",
            created_by=operator.id,
        )
    )
    db.commit()

    result = get_recent_incidents(operator_ctx, "R001")

    assert result.robot_id == "R001"
    assert len(result.incidents) >= 1
    assert result.incidents[0].title == "Overheating"


def test_get_recent_incidents_no_incidents_is_empty_list(db, operator_ctx):
    db.query(Incident).filter(Incident.robot_id == "R003").delete()
    db.commit()

    result = get_recent_incidents(operator_ctx, "R003")

    assert result.incidents == []


def test_get_recent_incidents_respects_limit(db, operator_ctx):
    operator = db.query(User).filter(User.username == "operator1").first()
    db.query(Incident).filter(Incident.robot_id == "R002").delete()
    for i in range(5):
        db.add(
            Incident(
                robot_id="R002",
                title=f"Issue {i}",
                description="x",
                severity="low",
                status="open",
                created_by=operator.id,
            )
        )
    db.commit()

    result = get_recent_incidents(operator_ctx, "R002", limit=2)

    assert len(result.incidents) == 2


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


class _FakeEmbeddingsClient:
    """Returns a fixed, pre-agreed vector regardless of input — lets the
    test control similarity ordering deterministically without ever calling
    the real Voyage API."""

    def __init__(self, vector):
        self._vector = vector

    def embed(self, texts, *, input_type):
        return [self._vector for _ in texts]


def test_search_documents_ranks_by_similarity(db, operator_ctx):
    from backend.app.agent import tools as tools_module

    operator = db.query(User).filter(User.username == "operator1").first()

    db.query(Document).filter(Document.title.like("Test Doc%")).delete(synchronize_session=False)
    db.commit()

    close_doc = Document(title="Test Doc Close", source="unit-test", uploaded_by=operator.id)
    far_doc = Document(title="Test Doc Far", source="unit-test", uploaded_by=operator.id)
    db.add_all([close_doc, far_doc])
    db.flush()

    dim = 1024
    query_vector = [1.0] + [0.0] * (dim - 1)
    close_vector = [0.99] + [0.01] * (dim - 1)
    far_vector = [0.0, 1.0] + [0.0] * (dim - 2)

    db.add(DocumentChunk(document_id=close_doc.id, chunk_index=0, chunk_text="closely related content", embedding=close_vector))
    db.add(DocumentChunk(document_id=far_doc.id, chunk_index=0, chunk_text="unrelated content", embedding=far_vector))
    db.commit()

    original = tools_module.get_embeddings_client
    tools_module.get_embeddings_client = lambda: _FakeEmbeddingsClient(query_vector)
    try:
        result = search_documents(operator_ctx, "what is closely related?", limit=2)
    finally:
        tools_module.get_embeddings_client = original

    assert result.results[0].document_title == "Test Doc Close"
    assert result.results[0].similarity > result.results[-1].similarity
