import json
import logging
import os
import time

from kafka import KafkaConsumer

from backend.app.observability.logging import configure_logging

# Must run before any other backend.app import that might log at import
# time, same rationale as backend/app/main.py.
configure_logging()

from backend.app.observability.tracing import configure_tracing

# Before kafka/sqlalchemy/redis are imported below, so their instrumentors
# see the real, unpatched modules first.
configure_tracing(service_name="robot-fleet-telemetry-consumer")

from opentelemetry import propagate
from opentelemetry.trace import Status, StatusCode

from backend.app.cache import TELEMETRY_CHANNEL, redis_client
from backend.app.database import SessionLocal
from backend.app.kafka import KAFKA_BOOTSTRAP_SERVERS, KAFKA_SECURITY_PROTOCOL, TELEMETRY_TOPIC
from backend.app.models.robot import Robot  # noqa: F401 - registers the `robots` table for Telemetry's FK
from backend.app.models.telemetry import Telemetry
from backend.app.observability.metrics import (
    kafka_message_processing_duration_seconds,
    kafka_messages_consumed_total,
    telemetry_events_processed_total,
    telemetry_events_received_total,
    telemetry_processing_duration_seconds,
    telemetry_processing_failures_total,
)
from backend.app.observability.metrics import REGISTRY
from backend.app.observability.tracing import get_tracer

CONSUMER_GROUP = "telemetry-writer"

# The consumer isn't an HTTP service like the API, so it needs its own tiny
# metrics HTTP server for Prometheus to scrape (see
# infrastructure/observability/prometheus/prometheus.yml's
# telemetry-consumer job) — the API's GET /metrics only serves the API
# process's own in-memory registry, not this process's.
METRICS_PORT = int(os.getenv("METRICS_PORT", "9100"))

logger = logging.getLogger("backend.app.telemetry_consumer")
tracer = get_tracer("backend.app.telemetry_consumer")


class _KafkaHeaderGetter:
    """Reads W3C tracecontext out of kafka-python's header format
    (list[tuple[str, bytes]]) — the same format/shape
    opentelemetry-instrumentation-kafka's own propagator reads, so a
    message it instrumented on the producer side extracts cleanly here.
    """

    def get(self, carrier, key: str):
        for item_key, value in carrier or []:
            if item_key == key and value is not None:
                return [value.decode()]
        return None

    def keys(self, carrier):
        return [key for key, _ in carrier or []]


_kafka_header_getter = _KafkaHeaderGetter()


def _save(event: dict):
    db = SessionLocal()
    try:
        db.add(
            Telemetry(
                robot_id=event["id"],
                battery=event["battery"],
                temperature=event["temperature"],
                x=event["x"],
                y=event["y"],
            )
        )
        db.commit()
    finally:
        db.close()


def _process(event: dict, headers=None) -> None:
    """Persist one telemetry event and fan it out to Redis pub/sub.

    Wrapped in its own span + histogram so a latency spike surfaced in
    Grafana ("telemetry_processing_duration_seconds is up") can be traced
    straight to whether the slow part was the DB write or the Redis
    publish, via this span's children.

    `headers` (raw Kafka message headers) let this span continue the
    producer's trace across the Kafka hop. This is done explicitly here,
    separately from opentelemetry-instrumentation-kafka's own consumer
    span, because that library's span is only current *inside* its
    `KafkaConsumer.__next__` wrapper — by the time `main()`'s for-loop body
    below runs and calls this function, that span (and its context) has
    already ended. Extracting the same headers again is the straightforward
    way to still land this span in the producer's trace instead of a new,
    disconnected one.
    """
    robot_id = event.get("id", "unknown")
    parent_context = propagate.extract(headers or [], getter=_kafka_header_getter)

    with tracer.start_as_current_span("telemetry.process", context=parent_context) as span:
        span.set_attribute("robot.id", robot_id)
        span.set_attribute("messaging.system", "kafka")
        span.set_attribute("messaging.destination", TELEMETRY_TOPIC)

        start = time.perf_counter()
        try:
            _save(event)
            redis_client.publish(TELEMETRY_CHANNEL, json.dumps(event))
        except Exception as exc:
            telemetry_processing_failures_total.labels(stage="process").inc()
            logger.exception("telemetry.process_failed", extra={"robot_id": robot_id})
            span.record_exception(exc)
            span.set_status(Status(StatusCode.ERROR))
            raise
        else:
            duration = time.perf_counter() - start
            telemetry_processing_duration_seconds.observe(duration)
            telemetry_events_processed_total.inc()
            logger.info(
                "telemetry.processed",
                extra={"robot_id": robot_id, "duration_ms": round(duration * 1000, 2)},
            )


def main():
    from prometheus_client import start_http_server

    start_http_server(METRICS_PORT, registry=REGISTRY)

    consumer = KafkaConsumer(
        TELEMETRY_TOPIC,
        bootstrap_servers=KAFKA_BOOTSTRAP_SERVERS,
        security_protocol=KAFKA_SECURITY_PROTOCOL,
        group_id=CONSUMER_GROUP,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
    )

    logger.info(
        "telemetry_consumer.started", extra={"topic": TELEMETRY_TOPIC, "metrics_port": METRICS_PORT}
    )

    try:
        for message in consumer:
            telemetry_events_received_total.inc()
            kafka_messages_consumed_total.labels(topic=TELEMETRY_TOPIC).inc()

            msg_start = time.perf_counter()
            try:
                _process(message.value, headers=message.headers)
            except Exception:
                # _process already logged/counted the failure; keep consuming
                # rather than let one bad event kill the consumer process.
                pass
            finally:
                kafka_message_processing_duration_seconds.labels(topic=TELEMETRY_TOPIC).observe(
                    time.perf_counter() - msg_start
                )
    except KeyboardInterrupt:
        logger.info("telemetry_consumer.stopped")
    finally:
        consumer.close()


if __name__ == "__main__":
    main()
