"""OpenTelemetry tracing setup, shared by the API, telemetry consumer, and
simulator processes.

Design notes:

- All three processes call `configure_tracing(service_name=...)` once at
  startup (mirrors `configure_logging()`). Each gets its own
  `service.name` resource attribute so traces/spans are attributable to
  "robot-fleet-api" vs "robot-fleet-telemetry-consumer" vs
  "robot-fleet-simulator" in Grafana/Tempo/Jaeger, matching how the rest of
  the stack (docker-compose service names, k8s Deployment names) already
  separates these three.
- Exporting is OTLP-over-gRPC to a collector, endpoint fully driven by the
  standard `OTEL_EXPORTER_OTLP_ENDPOINT` env var. If it's unset, tracing
  still initializes (so instrumented libraries/manual spans never crash the
  app) but spans are simply dropped (no-op exporter) — this keeps local
  `pytest` runs and any environment without a collector working exactly as
  before.
- Instrumentation is safe-by-default: any instrumentor that fails to import
  or apply (e.g. a library isn't installed in a given process) is caught
  and logged rather than crashing startup — tracing is additive, not a hard
  dependency for the app to run.
"""

import logging
import os

logger = logging.getLogger("backend.app.tracing")

_configured = False


def configure_tracing(service_name: str) -> None:
    """Initialize the global TracerProvider. Call once per process, early
    (before importing the libraries that get auto-instrumented).

    Idempotent — safe to call more than once (e.g. from tests) since a
    second call would otherwise raise from the SDK when a provider is
    already registered.
    """
    global _configured
    if _configured:
        return
    _configured = True

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                "service.namespace": "robot-fleet",
                "deployment.environment": os.getenv("DEPLOYMENT_ENVIRONMENT", "development"),
            }
        )
        provider = TracerProvider(resource=resource)

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if endpoint:
            # insecure=True: the collector is reached over the internal
            # docker/k8s network, not the public internet — no TLS needed
            # for a local/dev-style deployment. Revisit if the collector is
            # ever exposed across a less trusted network boundary.
            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("tracing.configured", extra={"otel_endpoint": endpoint})
        else:
            logger.info("tracing.configured_noop", extra={"reason": "OTEL_EXPORTER_OTLP_ENDPOINT unset"})

        trace.set_tracer_provider(provider)

        _instrument_common()
    except Exception:
        logger.exception("tracing.configure_failed")


def _instrument_common() -> None:
    """Auto-instrument libraries used by more than one process (SQLAlchemy,
    Redis, Kafka). FastAPI instrumentation is separate (see
    `instrument_fastapi`) since only the API process has a FastAPI app.
    """
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        from backend.app.database import engine

        SQLAlchemyInstrumentor().instrument(engine=engine)
    except Exception:
        logger.exception("tracing.instrument_failed", extra={"library": "sqlalchemy"})

    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception:
        logger.exception("tracing.instrument_failed", extra={"library": "redis"})

    try:
        from opentelemetry.instrumentation.kafka import KafkaInstrumentor

        KafkaInstrumentor().instrument()
    except Exception:
        logger.exception("tracing.instrument_failed", extra={"library": "kafka-python"})


def instrument_fastapi(app) -> None:
    """Auto-instrument the FastAPI app (API process only)."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(app, excluded_urls="health,health/ready,metrics")
    except Exception:
        logger.exception("tracing.instrument_failed", extra={"library": "fastapi"})


def get_tracer(name: str):
    """Small convenience wrapper so call sites don't each import `trace`."""
    from opentelemetry import trace

    return trace.get_tracer(name)
