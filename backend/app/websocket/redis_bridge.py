import json

import redis.asyncio as redis_async

from backend.app.cache import CACHE_HOST, CACHE_PORT, TELEMETRY_CHANNEL
from backend.app.websocket.manager import manager


async def listen_for_telemetry():
    client = redis_async.Redis(host=CACHE_HOST, port=CACHE_PORT, decode_responses=True)
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
