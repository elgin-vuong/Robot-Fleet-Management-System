import time

from backend.app.agent.confirmations import create_confirmation, pop_confirmation


def test_confirmation_round_trip():
    confirmation_id = create_confirmation(user_id=1, username="operator1", robot_id="R001", command="STOP")

    pending = pop_confirmation(confirmation_id)

    assert pending is not None
    assert pending["user_id"] == 1
    assert pending["username"] == "operator1"
    assert pending["robot_id"] == "R001"
    assert pending["command"] == "STOP"


def test_confirmation_is_single_use():
    confirmation_id = create_confirmation(user_id=1, username="operator1", robot_id="R001", command="STOP")

    first = pop_confirmation(confirmation_id)
    second = pop_confirmation(confirmation_id)

    assert first is not None
    assert second is None


def test_confirmation_unknown_id_returns_none():
    assert pop_confirmation("does-not-exist") is None


def test_confirmation_expires():
    # Bypass the fixed 60s TTL to prove expiry actually works without a slow test.
    from backend.app.agent.confirmations import _key
    from backend.app.cache import redis_client
    import json

    confirmation_id = "expiry-test"
    payload = {
        "user_id": 1,
        "username": "operator1",
        "robot_id": "R001",
        "command": "STOP",
        "created_at": "2026-01-01T00:00:00+00:00",
    }
    redis_client.set(_key(confirmation_id), json.dumps(payload), ex=1)

    time.sleep(1.5)

    assert pop_confirmation(confirmation_id) is None


def test_confirmation_for_one_command_does_not_leak_into_another():
    """A confirmation is scoped to an exact (user, robot, command) triple —
    distinct actions always get distinct, unrelated confirmation_ids, so
    there is no shared identifier a STOP confirmation could be replayed
    against for a START, or against a different robot.
    """
    stop_id = create_confirmation(user_id=1, username="operator1", robot_id="R001", command="STOP")
    start_id = create_confirmation(user_id=1, username="operator1", robot_id="R001", command="START")
    other_robot_id = create_confirmation(user_id=1, username="operator1", robot_id="R002", command="STOP")

    assert len({stop_id, start_id, other_robot_id}) == 3

    stop_pending = pop_confirmation(stop_id)
    assert stop_pending["command"] == "STOP"
    assert stop_pending["robot_id"] == "R001"

    # Popping the STOP/R001 confirmation must not have touched the others.
    start_pending = pop_confirmation(start_id)
    assert start_pending["command"] == "START"

    other_robot_pending = pop_confirmation(other_robot_id)
    assert other_robot_pending["robot_id"] == "R002"
