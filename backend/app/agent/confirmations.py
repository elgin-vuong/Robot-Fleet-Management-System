"""Durable, short-lived storage for pending write-action confirmations.

Uses the project's existing Redis client (backend/app/cache.py) rather than
in-process memory, so this works correctly even if the API runs as multiple
worker processes — a confirmation created by one worker must be confirmable
by a request that lands on a different worker.

A confirmation is bound to an exact (user, robot_id, command) triple and is
single-use: `pop_confirmation` atomically fetches-and-deletes the record
(Redis GETDEL), so two concurrent /agent/confirm calls for the same ID can
never both succeed, and expiry is handled natively by Redis's key TTL.
"""

import json
import uuid
from datetime import datetime, timezone

from backend.app.cache import redis_client

CONFIRMATION_TTL_SECONDS = 60
CONFIRMATION_KEY_PREFIX = "agent:confirmation:"


def _key(confirmation_id: str) -> str:
    return f"{CONFIRMATION_KEY_PREFIX}{confirmation_id}"


def create_confirmation(*, user_id: int, username: str, robot_id: str, command: str) -> str:
    """Store a pending write action and return its confirmation_id."""
    confirmation_id = uuid.uuid4().hex
    payload = {
        "user_id": user_id,
        "username": username,
        "robot_id": robot_id,
        "command": command,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    redis_client.set(_key(confirmation_id), json.dumps(payload), ex=CONFIRMATION_TTL_SECONDS)
    return confirmation_id


def pop_confirmation(confirmation_id: str) -> dict | None:
    """Atomically fetch and invalidate a pending confirmation.

    Returns None if it never existed, already expired, or was already
    consumed by a previous call — the caller can't distinguish those cases,
    which is intentional: all three should be reported the same safe way.
    """
    raw = redis_client.getdel(_key(confirmation_id))
    if raw is None:
        return None
    return json.loads(raw)
