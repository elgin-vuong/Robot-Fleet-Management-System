import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from backend.app.agent.exceptions import LLMProviderError
from backend.app.agent.llm_client import LLMTurnResult, ToolCall
from backend.app.cache import redis_client
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.command import Command
from backend.app.models.robot import Robot
from backend.app.models.user import User
from backend.app.routes.agent import get_llm_client

client = TestClient(app)


@pytest.fixture(autouse=True, scope="module")
def _reset_agent_rate_limits():
    # The rate limiter's and history's Redis keys have a real TTL and
    # persist across separate pytest invocations. Without this, re-running
    # this file (or the full suite) within that window can trip the rate
    # limit — or leak conversation history between otherwise-independent
    # tests — purely due to wall-clock timing from a previous run.
    for pattern in ("agent:ratelimit:*", "agent:history:*"):
        for key in redis_client.scan_iter(pattern):
            redis_client.delete(key)


class ScriptedLLMClient:
    """Replays a fixed sequence of LLMTurnResult objects, one per call.

    Standing in for a real provider in tests — nothing here makes a network
    call, so these tests run without any LLM credentials configured.
    Records the `messages` it was called with so tests can assert on what
    conversation history actually got sent.
    """

    def __init__(self, turns):
        self._turns = list(turns)
        self.call_count = 0
        self.received_messages: list[list[dict]] = []

    def generate_with_tools(self, *, system, messages, tools, max_tokens=1024):
        self.call_count += 1
        self.received_messages.append(messages)
        if not self._turns:
            raise AssertionError("ScriptedLLMClient ran out of scripted turns")
        return self._turns.pop(0)


class AlwaysRequestsToolLLMClient:
    """Never produces a final answer — used to prove the tool-call loop
    can't spin forever."""

    def generate_with_tools(self, *, system, messages, tools, max_tokens=1024):
        return LLMTurnResult(
            text=None,
            tool_calls=[ToolCall(id="t", name="get_fleet_summary", arguments={})],
            stop_reason="tool_use",
            raw_content=[{"type": "tool_use", "id": "t", "name": "get_fleet_summary", "input": {}}],
        )


class RaisingLLMClient:
    def generate_with_tools(self, *, system, messages, tools, max_tokens=1024):
        raise LLMProviderError("simulated provider outage")


@pytest.fixture
def use_llm_client():
    overridden = []

    def _use(fake_client):
        app.dependency_overrides[get_llm_client] = lambda: fake_client
        overridden.append(True)

    yield _use

    if overridden:
        del app.dependency_overrides[get_llm_client]


def _tool_use_turn(tool_name, arguments, call_id="t1", text=None):
    return LLMTurnResult(
        text=text,
        tool_calls=[ToolCall(id=call_id, name=tool_name, arguments=arguments)],
        stop_reason="tool_use",
        raw_content=[{"type": "tool_use", "id": call_id, "name": tool_name, "input": arguments}],
    )


def _final_text_turn(text):
    return LLMTurnResult(text=text, tool_calls=[], stop_reason="end_turn", raw_content=[{"type": "text", "text": text}])


# ---------------------------------------------------------------------------
# Basic auth requirement
# ---------------------------------------------------------------------------


def test_chat_requires_auth():
    response = client.post("/agent/chat", json={"message": "hello"})
    assert response.status_code == 401


def test_confirm_requires_auth():
    response = client.post("/agent/confirm", json={"confirmation_id": "whatever"})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Read flow
# ---------------------------------------------------------------------------


def test_read_only_chat_executes_tool_and_returns_final_answer(viewer_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [
            _tool_use_turn("get_fleet_summary", {}),
            _final_text_turn("The fleet has several robots online."),
        ]
    )
    use_llm_client(fake)

    response = client.post("/agent/chat", json={"message": "What robots are active?"}, headers=viewer_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["requires_confirmation"] is False
    assert body["confirmation_id"] is None
    assert body["response"] == "The fleet has several robots online."
    assert body["tool_calls"] == [{"tool": "get_fleet_summary", "status": "success", "detail": None}]


def test_malformed_tool_arguments_do_not_crash_the_server(viewer_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [
            _tool_use_turn("get_recent_telemetry", {"robot_id": "R001", "limit": "not-a-number"}),
            _final_text_turn("I couldn't read telemetry with that request."),
        ]
    )
    use_llm_client(fake)

    response = client.post("/agent/chat", json={"message": "show me telemetry"}, headers=viewer_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["tool_calls"][0]["status"] == "error"


def test_invalid_robot_in_read_tool_is_reported_not_fatal(viewer_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [
            _tool_use_turn("get_robot_status", {"robot_id": "R999"}),
            _final_text_turn("R999 does not exist in the fleet."),
        ]
    )
    use_llm_client(fake)

    response = client.post("/agent/chat", json={"message": "status of R999"}, headers=viewer_headers)

    assert response.status_code == 200
    assert response.json()["tool_calls"][0]["status"] == "error"


# ---------------------------------------------------------------------------
# Write flow / confirmation
# ---------------------------------------------------------------------------


def test_write_request_returns_confirmation_not_execution(operator_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [_tool_use_turn("send_robot_command", {"robot_id": "R001", "command": "STOP"}, text="Confirm stopping R001?")]
    )
    use_llm_client(fake)

    response = client.post("/agent/chat", json={"message": "Stop R001"}, headers=operator_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["requires_confirmation"] is True
    assert body["confirmation_id"]


def test_viewer_cannot_trigger_a_write_tool(viewer_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [
            _tool_use_turn("send_robot_command", {"robot_id": "R001", "command": "STOP"}),
            _final_text_turn("You don't have permission to send robot commands."),
        ]
    )
    use_llm_client(fake)

    response = client.post("/agent/chat", json={"message": "Stop R001"}, headers=viewer_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["requires_confirmation"] is False
    assert body["confirmation_id"] is None
    assert body["tool_calls"][0]["status"] == "error"


def test_write_request_for_invalid_robot_never_creates_a_confirmation(operator_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [
            _tool_use_turn("send_robot_command", {"robot_id": "R999", "command": "STOP"}),
            _final_text_turn("R999 was not found, so I can't stop it."),
        ]
    )
    use_llm_client(fake)

    response = client.post("/agent/chat", json={"message": "Stop R999"}, headers=operator_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["requires_confirmation"] is False
    assert body["confirmation_id"] is None


def test_full_confirm_flow_executes_via_existing_command_service(operator_headers, use_llm_client, request):
    db = SessionLocal()
    try:
        db.query(Command).filter(Command.robot_id == "R003").delete()
        db.commit()
    finally:
        db.close()

    fake = ScriptedLLMClient(
        [_tool_use_turn("send_robot_command", {"robot_id": "R003", "command": "START"})]
    )
    use_llm_client(fake)

    chat_response = client.post("/agent/chat", json={"message": "Start R003"}, headers=operator_headers)
    confirmation_id = chat_response.json()["confirmation_id"]
    assert confirmation_id

    confirm_response = client.post("/agent/confirm", json={"confirmation_id": confirmation_id}, headers=operator_headers)

    assert confirm_response.status_code == 200
    body = confirm_response.json()
    assert body["success"] is True
    assert body["robot_id"] == "R003"
    assert body["command"] == "START"

    db = SessionLocal()
    try:
        robot = db.get(Robot, "R003")
        assert robot.status == "MOVING"

        logged = db.query(Command).filter(Command.robot_id == "R003").all()
        assert len(logged) == 1
        assert logged[0].command == "START"
    finally:
        db.close()


def test_confirmation_executes_exactly_once(operator_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [_tool_use_turn("send_robot_command", {"robot_id": "R004", "command": "STOP"})]
    )
    use_llm_client(fake)

    chat_response = client.post("/agent/chat", json={"message": "Stop R004"}, headers=operator_headers)
    confirmation_id = chat_response.json()["confirmation_id"]

    first = client.post("/agent/confirm", json={"confirmation_id": confirmation_id}, headers=operator_headers)
    second = client.post("/agent/confirm", json={"confirmation_id": confirmation_id}, headers=operator_headers)

    assert first.status_code == 200
    assert second.status_code == 404


def test_confirm_rejects_wrong_user(operator_headers, admin_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [_tool_use_turn("send_robot_command", {"robot_id": "R005", "command": "STOP"})]
    )
    use_llm_client(fake)

    chat_response = client.post("/agent/chat", json={"message": "Stop R005"}, headers=operator_headers)
    confirmation_id = chat_response.json()["confirmation_id"]

    response = client.post("/agent/confirm", json={"confirmation_id": confirmation_id}, headers=admin_headers)

    assert response.status_code == 403


def test_confirm_rejects_unknown_confirmation_id(operator_headers):
    response = client.post("/agent/confirm", json={"confirmation_id": "nonexistent"}, headers=operator_headers)
    assert response.status_code == 404


def test_confirm_rechecks_role_at_execution_time(operator_headers, use_llm_client):
    """The confirmation was legitimately created while the user was an
    operator; if their role is revoked before they confirm, execution must
    still be blocked — permission is re-checked at confirm time, not just
    trusted from when the confirmation was created.
    """
    fake = ScriptedLLMClient(
        [_tool_use_turn("send_robot_command", {"robot_id": "R001", "command": "STOP"})]
    )
    use_llm_client(fake)

    chat_response = client.post("/agent/chat", json={"message": "Stop R001"}, headers=operator_headers)
    confirmation_id = chat_response.json()["confirmation_id"]

    db = SessionLocal()
    try:
        operator = db.query(User).filter(User.username == "operator1").first()
        operator.role = "viewer"
        db.commit()
    finally:
        db.close()

    try:
        response = client.post("/agent/confirm", json={"confirmation_id": confirmation_id}, headers=operator_headers)
        assert response.status_code == 403
    finally:
        db = SessionLocal()
        try:
            operator = db.query(User).filter(User.username == "operator1").first()
            operator.role = "operator"
            db.commit()
        finally:
            db.close()


def test_confirm_never_claims_success_when_execution_fails(operator_headers, use_llm_client):
    """If the underlying command service fails for any reason (e.g. the
    database is unavailable — standing in for Kafka being down, since this
    codebase's real command path is DB-only, not Kafka-backed), the agent
    must report failure, never a false success.
    """
    fake = ScriptedLLMClient(
        [_tool_use_turn("send_robot_command", {"robot_id": "R002", "command": "START"})]
    )
    use_llm_client(fake)

    chat_response = client.post("/agent/chat", json={"message": "Start R002"}, headers=operator_headers)
    confirmation_id = chat_response.json()["confirmation_id"]

    with patch("backend.app.routes.agent.send_robot_command", side_effect=RuntimeError("db unavailable")):
        response = client.post("/agent/confirm", json={"confirmation_id": confirmation_id}, headers=operator_headers)

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is False
    assert "could not" in body["response"].lower()


# ---------------------------------------------------------------------------
# Conversation history
# ---------------------------------------------------------------------------


def test_conversation_history_is_sent_on_the_next_request(operator_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [
            _final_text_turn("Robot R001 is stopped."),
            _final_text_turn("It was stopped because an operator sent a STOP command."),
        ]
    )
    use_llm_client(fake)

    first = client.post("/agent/chat", json={"message": "Why is R001 stopped?"}, headers=operator_headers)
    assert first.status_code == 200

    second = client.post("/agent/chat", json={"message": "yes, tell me more"}, headers=operator_headers)
    assert second.status_code == 200

    # Without history threading, the second call would only ever see
    # "yes, tell me more" with nothing to attach it to.
    second_call_messages = fake.received_messages[1]
    flattened = json.dumps(second_call_messages)
    assert "Why is R001 stopped?" in flattened
    assert "Robot R001 is stopped." in flattened


def test_reset_chat_clears_history(operator_headers, use_llm_client):
    fake = ScriptedLLMClient(
        [
            _final_text_turn("Robot R001 is stopped."),
            _final_text_turn("Sure, what would you like to know?"),
        ]
    )
    use_llm_client(fake)

    client.post("/agent/chat", json={"message": "Why is R001 stopped?"}, headers=operator_headers)

    reset_response = client.delete("/agent/chat", headers=operator_headers)
    assert reset_response.status_code == 204

    client.post("/agent/chat", json={"message": "yes"}, headers=operator_headers)

    second_call_messages = fake.received_messages[1]
    flattened = json.dumps(second_call_messages)
    assert "Why is R001 stopped?" not in flattened


def test_history_survives_a_confirmation_turn_without_corrupting_the_next_request(operator_headers, use_llm_client):
    """A write-tool turn produces a dangling tool_use with no executed
    result. If that ever gets persisted without a matching tool_result, the
    next request's transcript would be malformed. This proves the app
    still works normally on the request right after a confirmation was
    requested.
    """
    fake = ScriptedLLMClient(
        [
            _tool_use_turn("send_robot_command", {"robot_id": "R001", "command": "STOP"}),
            _final_text_turn("Sure — what else would you like to know?"),
        ]
    )
    use_llm_client(fake)

    first = client.post("/agent/chat", json={"message": "Stop R001"}, headers=operator_headers)
    assert first.status_code == 200
    assert first.json()["requires_confirmation"] is True

    second = client.post("/agent/chat", json={"message": "actually never mind, tell me about R002"}, headers=operator_headers)
    assert second.status_code == 200
    assert second.json()["response"] == "Sure — what else would you like to know?"


# ---------------------------------------------------------------------------
# Loop protection / provider failure
# ---------------------------------------------------------------------------


def test_max_tool_calls_is_enforced(viewer_headers, use_llm_client):
    use_llm_client(AlwaysRequestsToolLLMClient())

    response = client.post("/agent/chat", json={"message": "loop forever"}, headers=viewer_headers)

    assert response.status_code == 400


def test_llm_provider_error_returns_safe_503(viewer_headers, use_llm_client):
    use_llm_client(RaisingLLMClient())

    response = client.post("/agent/chat", json={"message": "hello"}, headers=viewer_headers)

    assert response.status_code == 503
    # Never leak internal exception detail/stack traces to the client.
    assert "simulated provider outage" not in response.text
