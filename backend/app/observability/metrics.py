"""Prometheus metrics for the API, telemetry consumer, and simulator.

One shared `CollectorRegistry` (the library's default) is used by all
processes; only the API process exposes it over HTTP (`GET /metrics` in
backend/app/main.py) since that's the only process Prometheus can reach —
the consumer and simulator are not HTTP services (see docker-compose.yml's
comment on why they have no healthcheck either). Their counters still exist
in-process mainly so unit tests can assert on them directly; if per-process
scraping of the consumer/simulator is wanted later, the fix is a tiny
`prometheus_client.start_http_server()` in their entrypoints, not a
different metrics layer.

Label cardinality: robot IDs are deliberately never used as a label value
anywhere in this module (per the fleet's small, fixed robot count today this
would be "fine" in practice, but it's the kind of thing that quietly becomes
a cardinality problem the moment the fleet grows or gets dynamic IDs). Robot
identity belongs in logs/traces, not metric labels.
"""

import os

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)
from starlette.responses import Response

REGISTRY = CollectorRegistry(auto_describe=True)

# --- HTTP -------------------------------------------------------------

http_requests_total = Counter(
    "http_requests_total",
    "Total HTTP requests handled by the API.",
    ["method", "route", "status_code"],
    registry=REGISTRY,
)

http_request_duration_seconds = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds.",
    ["method", "route"],
    registry=REGISTRY,
)

http_requests_in_flight = Gauge(
    "http_requests_in_flight",
    "HTTP requests currently being processed.",
    registry=REGISTRY,
)

# --- Telemetry (consumer) ----------------------------------------------

telemetry_events_received_total = Counter(
    "telemetry_events_received_total",
    "Telemetry events read off Kafka by the consumer.",
    registry=REGISTRY,
)

telemetry_events_processed_total = Counter(
    "telemetry_events_processed_total",
    "Telemetry events successfully persisted and published to Redis.",
    registry=REGISTRY,
)

telemetry_processing_failures_total = Counter(
    "telemetry_processing_failures_total",
    "Telemetry events that failed to process.",
    ["stage"],
    registry=REGISTRY,
)

telemetry_processing_duration_seconds = Histogram(
    "telemetry_processing_duration_seconds",
    "Time to persist + publish a single telemetry event.",
    registry=REGISTRY,
)

# --- Kafka (producer + consumer, shared across API/simulator/consumer) --

kafka_messages_published_total = Counter(
    "kafka_messages_published_total",
    "Messages published to Kafka.",
    ["topic"],
    registry=REGISTRY,
)

kafka_messages_consumed_total = Counter(
    "kafka_messages_consumed_total",
    "Messages consumed from Kafka.",
    ["topic"],
    registry=REGISTRY,
)

kafka_consumer_failures_total = Counter(
    "kafka_consumer_failures_total",
    "Consumer processing failures, by topic.",
    ["topic"],
    registry=REGISTRY,
)

kafka_message_processing_duration_seconds = Histogram(
    "kafka_message_processing_duration_seconds",
    "Time to process a single consumed Kafka message end-to-end.",
    ["topic"],
    registry=REGISTRY,
)

# --- Robot commands ------------------------------------------------------

robot_commands_requested_total = Counter(
    "robot_commands_requested_total",
    "Robot commands requested via the API or AI agent.",
    ["command"],
    registry=REGISTRY,
)

robot_commands_processed_total = Counter(
    "robot_commands_processed_total",
    "Robot commands successfully applied.",
    ["command"],
    registry=REGISTRY,
)

robot_commands_failed_total = Counter(
    "robot_commands_failed_total",
    "Robot commands that failed validation or execution.",
    ["command"],
    registry=REGISTRY,
)

# --- WebSocket -----------------------------------------------------------

websocket_active_connections = Gauge(
    "websocket_active_connections",
    "Currently open WebSocket connections.",
    registry=REGISTRY,
)

websocket_messages_sent_total = Counter(
    "websocket_messages_sent_total",
    "Messages broadcast to WebSocket clients.",
    registry=REGISTRY,
)

websocket_connection_failures_total = Counter(
    "websocket_connection_failures_total",
    "WebSocket sends that failed (stale/closed connections).",
    registry=REGISTRY,
)

# --- Fleet health ----------------------------------------------------------

fleet_robots_active = Gauge(
    "fleet_robots_active",
    "Number of robots currently known to the fleet.",
    registry=REGISTRY,
)

fleet_robots_unhealthy = Gauge(
    "fleet_robots_unhealthy",
    "Number of robots considered unhealthy (low battery or an open high/critical severity incident).",
    registry=REGISTRY,
)

# A robot below this battery percentage counts as unhealthy for the
# fleet_robots_unhealthy gauge. Environment-driven so ops can tune it
# without a code change.
UNHEALTHY_BATTERY_THRESHOLD = float(os.getenv("FLEET_UNHEALTHY_BATTERY_THRESHOLD", "15"))


def metrics_endpoint() -> Response:
    """Render the shared registry in Prometheus text exposition format."""
    return Response(generate_latest(REGISTRY), media_type=CONTENT_TYPE_LATEST)


def refresh_fleet_gauges(db) -> None:
    """Recompute the fleet-health gauges from current Postgres state.

    Called periodically from the API process (see main.py's lifespan) since
    that's where a DB session is cheaply available on a timer. Kept as a
    plain function taking a `Session` (rather than owning its own) so it's
    easy to unit test without spinning up the app.
    """
    from sqlalchemy import func

    from backend.app.models.incident import Incident
    from backend.app.models.robot import Robot

    total = db.query(func.count(Robot.id)).scalar() or 0
    low_battery = (
        db.query(func.count(Robot.id)).filter(Robot.battery < UNHEALTHY_BATTERY_THRESHOLD).scalar() or 0
    )
    critical_incident_robots = (
        db.query(func.count(func.distinct(Incident.robot_id)))
        .filter(Incident.status == "open", Incident.severity.in_(("high", "critical")))
        .scalar()
        or 0
    )

    fleet_robots_active.set(total)
    # Not a precise union (a robot could hit both conditions) but an upper
    # bound that's cheap to compute and good enough for an at-a-glance
    # dashboard gauge; exact overlap isn't worth a more complex query here.
    fleet_robots_unhealthy.set(min(total, low_battery + critical_incident_robots))
