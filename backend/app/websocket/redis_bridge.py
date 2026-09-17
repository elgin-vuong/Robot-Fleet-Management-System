import json

import redis.asyncio as redis_async

from backend.app.cache import REDIS_URL, TELEMETRY_CHANNEL
from backend.app.websocket.manager import manager


async def listen_for_telemetry():
    client = redis_async.Redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(TELEMETRY_CHANNEL)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            payload = json.loads(message["data"])
            await manager.broadcast({"type": "telemetry", "robot": payload})
    finally:
        await pubsub.unsubscribe(TELEMETRY_CHANNEL)
        await client.aclose()
