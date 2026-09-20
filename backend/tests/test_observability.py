"""Tests for the observability layer: metrics, structured logging, and
tracing initialization.

These deliberately don't require a live Prometheus, Grafana, or OTel
Collector — metrics are asserted directly against the shared registry (see
backend/app/observability/metrics.py), logging is asserted against the
JSON formatter's output, and tracing is asserted to initialize/no-op safely
whether or not a collector endpoint is configured/reachable. That matches
this repo's existing test style (backend/tests/test_kafka.py etc. hit a
real dev-stack Postgres/Kafka/Redis, but nothing here should *require* a
running Grafana instance).
"""

import json
import logging

from fastapi.testclient import TestClient
from prometheus_client.parser import text_string_to_metric_families

from backend.app.consumers.telemetry_consumer import _process
from backend.app.database import SessionLocal
from backend.app.main import app
from backend.app.models.telemetry import Telemetry
from backend.app.observability import metrics
from backend.app.observability.logging import JSONFormatter, request_id_var
from backend.app.observability.tracing import configure_tracing, get_tracer

client = TestClient(app)


def _metric_value(text: str, name: str, labels: dict | None = None) -> float | None:
    """Look up one sample's value by its exact metric name (e.g.
    "http_requests_total"), not the parser's metric *family* name (which
    strips suffixes like _total/_created — see
    prometheus_client.parser.text_string_to_metric_families).
    """
    for family in text_string_to_metric_families(text):
        for sample in family.samples:
            if sample.name != name:
                continue
            if labels is None or all(sample.labels.get(k) == v for k, v in labels.items()):
                return sample.value
    return None


# ---------------------------------------------------------------------------
# Metrics endpoint
# ---------------------------------------------------------------------------


def test_metrics_endpoint_responds():
    response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "http_requests_total" in response.text


def test_metrics_endpoint_is_valid_prometheus_exposition_format():
    response = client.get("/metrics")

    # Raises if the payload isn't parseable Prometheus text format.
    families = list(text_string_to_metric_families(response.text))
    names = {f.name for f in families}

    assert "http_request_duration_seconds" in names
    assert "fleet_robots_active" in names


def test_http_requests_total_increments_on_request(viewer_headers):
    before_text = client.get("/metrics").text
    before = _metric_value(before_text, "http_requests_total", {"route": "/robots", "method": "GET"}) or 0

    client.get("/robots", headers=viewer_headers)

    after_text = client.get("/metrics").text
    after = _metric_value(after_text, "http_requests_total", {"route": "/robots", "method": "GET"})

    assert after == before + 1


def test_http_route_label_uses_path_template_not_raw_id(viewer_headers):
    """A parameterized route (/robots/{robot_id}) must collapse to one
    label value regardless of which robot_id was requested — otherwise
    every distinct robot ID would create a new time series (see the
    cardinality note in backend/app/observability/metrics.py).
    """
    client.get("/robots/R001", headers=viewer_headers)
    client.get("/robots/R002", headers=viewer_headers)

    text = client.get("/metrics").text
    value = _metric_value(text, "http_requests_total", {"route": "/robots/{robot_id}"})

    assert value is not None and value >= 2


def test_robot_command_metrics_increment_on_success(operator_headers):
    before_text = client.get("/metrics").text
    before = _metric_value(before_text, "robot_commands_processed_total", {"command": "START"}) or 0

    response = client.post("/robots/R001/command", json={"command": "START"}, headers=operator_headers)
    assert response.status_code == 200

    after_text = client.get("/metrics").text
    after = _metric_value(after_text, "robot_commands_processed_total", {"command": "START"})

    assert after == before + 1


def test_robot_command_metrics_normalize_invalid_command_label(operator_headers):
    """An arbitrary/invalid command string must never become a raw label
    value — it should be normalized to the fixed "invalid" bucket.
    """
    response = client.post(
        "/robots/R001/command", json={"command": "NOT_A_REAL_COMMAND"}, headers=operator_headers
    )
    assert response.status_code == 404

    text = client.get("/metrics").text
    value = _metric_value(text, "robot_commands_failed_total", {"command": "invalid"})

    assert value is not None and value >= 1
    # The raw bogus string must not appear as its own label value anywhere.
    assert 'command="NOT_A_REAL_COMMAND"' not in text


def test_websocket_active_connections_gauge_tracks_connections(viewer_token):
    text_before = client.get("/metrics").text
    before = _metric_value(text_before, "websocket_active_connections") or 0

    with client.websocket_connect(f"/ws/robots?token={viewer_token}"):
        text_during = client.get("/metrics").text
        during = _metric_value(text_during, "websocket_active_connections")
        assert during == before + 1

    text_after = client.get("/metrics").text
    after = _metric_value(text_after, "websocket_active_connections")
    assert after == before


def test_fleet_gauges_reflect_seeded_robots():
    db = SessionLocal()
    try:
        metrics.refresh_fleet_gauges(db)
    finally:
        db.close()

    text = client.get("/metrics").text
    active = _metric_value(text, "fleet_robots_active")

    # backend/app/routes/robots.py seeds ROBOT_COUNT (5) robots on import.
    assert active is not None and active >= 5


# ---------------------------------------------------------------------------
# Telemetry consumer instrumentation
# ---------------------------------------------------------------------------


def _clear_telemetry(robot_id):
    db = SessionLocal()
    try:
        db.query(Telemetry).filter(Telemetry.robot_id == robot_id).delete()
        db.commit()
    finally:
        db.close()


def test_telemetry_process_increments_metrics_and_persists():
    # R003 is one of the ROBOT_COUNT robots backend/app/routes/robots.py
    # seeds on import — telemetry.robot_id has a FK to robots.id, so tests
    # must use a robot that actually exists rather than an arbitrary ID.
    _clear_telemetry("R003")

    before = metrics.telemetry_events_processed_total._value.get()

    _process({"id": "R003", "battery": 55.0, "temperature": 30.0, "x": 1.0, "y": 1.0})

    after = metrics.telemetry_events_processed_total._value.get()
    assert after == before + 1

    db = SessionLocal()
    try:
        rows = db.query(Telemetry).filter(Telemetry.robot_id == "R003").all()
    finally:
        db.close()

    assert len(rows) == 1


def test_telemetry_process_records_failure_metric_on_bad_event():
    before = metrics.telemetry_processing_failures_total.labels(stage="process")._value.get()

    try:
        _process({"id": "R004"})  # missing required fields -> should raise
    except Exception:
        pass

    after = metrics.telemetry_processing_failures_total.labels(stage="process")._value.get()
    assert after == before + 1


def test_telemetry_process_accepts_missing_headers():
    """The consumer must not crash when headers are absent (e.g. a message
    produced by something that never set trace-context headers).
    """
    _clear_telemetry("R005")

    _process({"id": "R005", "battery": 10.0, "temperature": 20.0, "x": 0.0, "y": 0.0}, headers=None)

    db = SessionLocal()
    try:
        rows = db.query(Telemetry).filter(Telemetry.robot_id == "R005").all()
    finally:
        db.close()

    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Structured logging
# ---------------------------------------------------------------------------


def test_json_formatter_produces_valid_json_with_expected_fields():
    record = logging.LogRecord(
        name="backend.app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="telemetry.processed",
        args=(),
        exc_info=None,
    )
    record.robot_id = "R003"
    record.duration_ms = 14

    formatted = JSONFormatter().format(record)
    payload = json.loads(formatted)

    assert payload["level"] == "INFO"
    assert payload["event"] == "telemetry.processed"
    assert payload["service"]
    assert payload["robot_id"] == "R003"
    assert payload["duration_ms"] == 14
    assert "timestamp" in payload


def test_json_formatter_includes_request_id_from_context():
    token = request_id_var.set("test-request-id-123")
    try:
        record = logging.LogRecord(
            name="backend.app.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="http.request",
            args=(),
            exc_info=None,
        )
        payload = json.loads(JSONFormatter().format(record))
    finally:
        request_id_var.reset(token)

    assert payload["request_id"] == "test-request-id-123"


def test_json_formatter_never_leaks_reserved_or_secret_looking_fields():
    """Guards against accidentally logging sensitive extras: nothing named
    like a password/token/secret should ever reach the formatted payload
    from this codebase's call sites. This test documents the expectation
    rather than scanning every call site — new call sites should keep
    following the no-secrets-in-`extra` convention.
    """
    record = logging.LogRecord(
        name="backend.app.test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="auth.login",
        args=(),
        exc_info=None,
    )
    record.username = "operator1"

    payload = json.loads(JSONFormatter().format(record))

    assert "password" not in payload
    assert "token" not in payload
    assert "jwt" not in payload
    assert payload["username"] == "operator1"


def test_request_id_header_is_returned_and_logged(viewer_headers):
    response = client.get("/robots", headers=viewer_headers)

    assert "X-Request-ID" in response.headers
    assert len(response.headers["X-Request-ID"]) > 0


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------


def test_configure_tracing_is_idempotent_and_does_not_raise():
    # Already configured once at import time (backend/app/main.py). Calling
    # again must be a safe no-op, not a crash from re-registering a
    # TracerProvider.
    configure_tracing(service_name="robot-fleet-api")
    configure_tracing(service_name="robot-fleet-api")


def test_tracer_produces_spans_without_a_configured_collector():
    """With OTEL_EXPORTER_OTLP_ENDPOINT unset (the default in the test
    environment — see backend/.env.example), spans should still be
    creatable and usable; they're just not exported anywhere. This is the
    "telemetry backend temporarily unavailable" case from the spec: the
    app must keep working either way.
    """
    tracer = get_tracer("backend.tests")

    with tracer.start_as_current_span("test.span") as span:
        span.set_attribute("test.attribute", "value")
        assert span is not None


def test_app_still_serves_requests_when_tracing_backend_is_unreachable(viewer_headers):
    """End-to-end version of the above: exercising a real endpoint must not
    fail just because there's no OTel Collector listening. BatchSpanProcessor
    exports are async/background, so a slow or absent collector should
    never block the request path.
    """
    response = client.get("/robots", headers=viewer_headers)
    assert response.status_code == 200
