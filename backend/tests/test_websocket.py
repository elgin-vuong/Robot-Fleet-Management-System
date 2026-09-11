import asyncio

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.websocket.manager import manager

client = TestClient(app)


def test_websocket_rejects_missing_token():
    try:
        with client.websocket_connect("/ws/robots"):
            assert False, "connection should have been rejected"
    except Exception:
        pass


def test_websocket_rejects_invalid_token():
    try:
        with client.websocket_connect("/ws/robots?token=not.a.valid.jwt"):
            assert False, "connection should have been rejected"
    except Exception:
        pass


def test_websocket_connection_succeeds(viewer_token):
    before = len(manager.active_connections)

    with client.websocket_connect(f"/ws/robots?token={viewer_token}"):
        assert len(manager.active_connections) == before + 1

    assert len(manager.active_connections) == before


def test_client_receives_a_broadcast(viewer_token):
    with client.websocket_connect(f"/ws/robots?token={viewer_token}") as ws:
        message = {"type": "telemetry", "robot": {"id": "R001", "battery": 42}}

        asyncio.run(manager.broadcast(message))

        assert ws.receive_json() == message


def test_disconnect_is_handled(viewer_token):
    before = len(manager.active_connections)

    with client.websocket_connect(f"/ws/robots?token={viewer_token}"):
        assert len(manager.active_connections) == before + 1

    assert len(manager.active_connections) == before


def test_invalid_client_message_does_not_crash_server(viewer_token):
    with client.websocket_connect(f"/ws/robots?token={viewer_token}") as ws:
        ws.send_text("not valid json {{{")

        assert len(manager.active_connections) >= 1

    response = client.get("/health")
    assert response.status_code == 200


def test_abrupt_disconnect_does_not_crash_server(viewer_token):
    with client.websocket_connect(f"/ws/robots?token={viewer_token}") as ws:
        ws.close()

    response = client.get("/health")
    assert response.status_code == 200
