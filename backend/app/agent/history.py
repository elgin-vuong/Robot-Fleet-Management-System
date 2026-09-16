"""Redis-backed conversation history.

Not RAG — this has nothing to do with retrieving documents or external
knowledge. It's just remembering what was already said earlier in the same
conversation, so a follow-up like "yes" or "tell me more about that" has
something to attach to. Without this, every /agent/chat call was a
brand-new, context-free request to the model.

Uses the same Redis instance as everything else (backend/app/cache.py) and
the same "durable but short-lived, keyed by user" pattern as
backend/app/agent/confirmations.py — a sliding TTL means an abandoned
conversation just quietly expires rather than accumulating forever.
"""

import json

from backend.app.cache import redis_client

HISTORY_TTL_SECONDS = 30 * 60  # refreshed on every message; expires after 30 min idle
MAX_HISTORY_MESSAGES = 20  # caps both Redis storage and per-request token usage


def _key(user_id: int) -> str:
    return f"agent:history:{user_id}"


def get_history(user_id: int) -> list[dict]:
    raw = redis_client.get(_key(user_id))
    if raw is None:
        return []
    return json.loads(raw)


def save_history(user_id: int, messages: list[dict]) -> None:
    redis_client.set(_key(user_id), json.dumps(messages[-MAX_HISTORY_MESSAGES:]), ex=HISTORY_TTL_SECONDS)


def clear_history(user_id: int) -> None:
    redis_client.delete(_key(user_id))
