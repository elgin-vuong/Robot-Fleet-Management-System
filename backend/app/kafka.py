import json
import os

from kafka import KafkaProducer

from backend.app.observability.metrics import kafka_messages_published_total

KAFKA_BOOTSTRAP_SERVERS = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
KAFKA_SECURITY_PROTOCOL = os.getenv("KAFKA_SECURITY_PROTOCOL", "PLAINTEXT")
TELEMETRY_TOPIC = "robot.telemetry"

_producer = None


def get_producer() -> KafkaProducer:
    global _producer

    if _producer is None:
        _producer = KafkaProducer(
            bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
            security_protocol=KAFKA_SECURITY_PROTOCOL,
            value_serializer=lambda v: json.dumps(v).encode("utf-8"),
            key_serializer=lambda k: k.encode("utf-8") if k is not None else None,
        )

    return _producer


def publish(topic: str, key: str | None, value: dict) -> None:
    """Publish a message and record the `kafka_messages_published_total`
    metric in one place, so every producer call site (simulator, API) gets
    the metric for free instead of remembering to increment it themselves.

    Trace context propagation onto the message (so the consumer can
    continue the same trace) is handled by KafkaInstrumentor, which patches
    KafkaProducer.send itself — see backend/app/observability/tracing.py —
    so there's nothing to do here for that part.
    """
    get_producer().send(topic, key=key, value=value)
    kafka_messages_published_total.labels(topic=topic).inc()
