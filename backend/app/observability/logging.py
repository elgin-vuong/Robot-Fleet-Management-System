"""Structured (JSON) logging shared by the API, telemetry consumer, and simulator.

All three processes run from the same image (see backend/Dockerfile) but have
separate entrypoints, so logging is configured once here and imported by each
entrypoint (backend/app/main.py, backend/app/consumers/telemetry_consumer.py,
backend/simulator/run.py) rather than relying on FastAPI/uvicorn to set it up.

Log records already follow a `logger.info("dotted.event.name", extra={...})`
convention across the codebase (see backend/app/routes/agent.py etc.) — this
module changes *how* those records are rendered (JSON instead of plain text)
without requiring call-site changes. New fields (trace/span id, request id)
are attached automatically when available via contextvars, so call sites
don't need to thread them through manually.
"""

import json
import logging
import os
import sys
from contextvars import ContextVar
from datetime import datetime, timezone

# Populated per-request (HTTP middleware) / per-message (Kafka consumers) so
# that any log statement emitted while handling that unit of work is
# automatically tagged, without every call site passing it explicitly.
request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

# Attributes on Python's LogRecord that are already handled explicitly or are
# CPython internals we don't want to leak into the JSON payload verbatim.
_RESERVED_RECORD_ATTRS = frozenset(
    logging.LogRecord(
        name="", level=0, pathname="", lineno=0, msg="", args=(), exc_info=None
    ).__dict__.keys()
) | {"message", "asctime", "taskName"}

SERVICE_NAME = os.getenv("OTEL_SERVICE_NAME", "robot-fleet-backend")


class JSONFormatter(logging.Formatter):
    """Renders each LogRecord as one JSON object per line.

    Trace/span IDs are read lazily from the current OpenTelemetry span (if
    the tracing module has been initialized and a span is active) so that
    logs emitted anywhere during a traced operation can be pivoted to from
    Grafana Tempo/Jaeger without every logger call needing to fetch them.
    """

    def format(self, record: logging.LogRecord) -> str:
        # Not self.formatTime(): that delegates to time.strftime, which
        # doesn't support %f (microseconds) — datetime.strftime does.
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        payload = {
            "timestamp": timestamp,
            "level": record.levelname,
            "service": SERVICE_NAME,
            "logger": record.name,
            "event": record.getMessage(),
        }

        request_id = request_id_var.get()
        if request_id is not None:
            payload["request_id"] = request_id

        trace_id, span_id = _current_trace_ids()
        if trace_id:
            payload["trace_id"] = trace_id
            payload["span_id"] = span_id

        for key, value in record.__dict__.items():
            if key in _RESERVED_RECORD_ATTRS or key in payload:
                continue
            payload[key] = value

        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(payload, default=str)


def _current_trace_ids() -> tuple[str | None, str | None]:
    """Best-effort read of the active OTel span's trace/span IDs.

    Isolated in its own function so a missing/uninitialized OTel SDK never
    breaks logging — observability is additive, not a hard dependency for
    the app to run.
    """
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context()

        if ctx is None or not ctx.is_valid:
            return None, None

        return format(ctx.trace_id, "032x"), format(ctx.span_id, "016x")
    except Exception:
        return None, None


def configure_logging() -> None:
    """Install JSON logging on the root logger. Call once per process, early.

    Idempotent: safe to call multiple times (e.g. once from app import time
    and once from a test fixture) without duplicating handlers.
    """
    root = logging.getLogger()
    level_name = os.getenv("LOG_LEVEL", "INFO").upper()
    root.setLevel(getattr(logging, level_name, logging.INFO))

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JSONFormatter())

    root.handlers = [handler]

    # Quiet down noisy third-party loggers that would otherwise duplicate
    # what our own request/consumer logging already records.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
