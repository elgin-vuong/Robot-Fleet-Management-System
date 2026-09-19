import json

import redis.asyncio as redis_async

from backend.app.cache import REDIS_URL, TELEMETRY_CHANNEL
from backend.app.observability.tracing import get_tracer
from backend.app.websocket.manager import manager

tracer = get_tracer("backend.app.websocket")


async def listen_for_telemetry():
    client = redis_async.Redis.from_url(REDIS_URL, decode_responses=True)
    pubsub = client.pubsub()
    await pubsub.subscribe(TELEMETRY_CHANNEL)

    try:
        async for message in pubsub.listen():
            if message["type"] != "message":
                continue

            payload = json.loads(message["data"])

            # New span rather than a continuation of the telemetry-consumer's
            # trace: pub/sub carries no trace context (unlike the Kafka hop,
            # which the KafkaInstrumentor propagates via message headers),
            # and this fan-out to N WebSocket clients is its own unit of
            # work rather than a child of any one telemetry event anyway.
            with tracer.start_as_current_span("websocket.broadcast_telemetry") as span:
                span.set_attribute("robot.id", payload.get("id", "unknown"))
                await manager.broadcast({"type": "telemetry", "robot": payload})
    finally:
        await pubsub.unsubscribe(TELEMETRY_CHANNEL)
        await client.aclose()
