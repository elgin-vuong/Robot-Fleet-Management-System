# Observability

How metrics, distributed tracing, and structured logging work in this
platform, how to run the stack, and how to verify each piece is working.

## Architecture

```
                         ┌─────────────────────────────────────────────┐
                         │              Application Services            │
                         │                                               │
                         │  robot-fleet-api (FastAPI)                    │
                         │  robot-fleet-telemetry-consumer               │
                         │  robot-fleet-simulator                        │
                         └───────────────┬─────────────┬────────────────┘
                                          │             │
                    metrics (Prometheus  │             │  traces (OTLP/gRPC)
                    text format, pulled) │             │  (pushed)
                                          ▼             ▼
                              ┌──────────────┐   ┌─────────────────┐
                              │  Prometheus   │   │ OTel Collector  │
                              │  (scrapes     │   │ (batches, then  │
                              │  :8000/metrics│   │ forwards)       │
                              │  and :9100)   │   └────────┬────────┘
                              └───────┬───────┘            │
                                      │                     ▼
                                      │              ┌─────────────┐
                                      │              │   Jaeger    │
                                      │              │ (trace UI)  │
                                      │              └──────┬──────┘
                                      ▼                     │
                              ┌───────────────┐             │
                              │    Grafana    │◄────────────┘
                              │ (dashboards,  │   (Jaeger datasource,
                              │  Prometheus + │    for pivoting from a
                              │  Jaeger       │    metric to a trace)
                              │  datasources) │
                              └───────────────┘

  Structured JSON logs go to stdout on every process (captured by
  `docker logs` / `kubectl logs`) and carry the same trace_id/span_id the
  Collector/Jaeger use, so a log line and a trace can be cross-referenced
  by hand without another moving part.
```

Three Python processes share one codebase and one observability layer
(`backend/app/observability/`):

| Process | Entrypoint | Role |
|---|---|---|
| API | `backend/app/main.py` (`uvicorn`) | HTTP + WebSocket, robot commands |
| Telemetry consumer | `backend/app/consumers/telemetry_consumer.py` | Kafka → Postgres → Redis pub/sub |
| Simulator | `backend/simulator/run.py` | Generates fake robot telemetry onto Kafka |

Each calls the same `configure_logging()` / `configure_tracing()` at
startup, so all three get JSON logs and OTLP tracing for free, with a
`service.name` (`robot-fleet-api` / `-telemetry-consumer` / `-simulator`)
that tells them apart in Jaeger and Grafana.

## Running the stack

```bash
docker compose up -d --build
```

This starts the application (Postgres, Redis, Kafka, backend, telemetry
consumer, simulator, frontend) **and** the observability stack (OTel
Collector, Jaeger, Prometheus, Grafana) together — nothing extra to run.

| Service | URL | Notes |
|---|---|---|
| App | http://localhost:8080 | React dashboard |
| Backend API | http://localhost:8000 | `/health`, `/health/ready`, `/metrics` |
| **Grafana** | **http://localhost:3000** | login `admin` / `admin` (or `$GRAFANA_ADMIN_PASSWORD`) |
| **Prometheus** | **http://localhost:9090** | raw metrics/targets UI |
| **Jaeger** | **http://localhost:16686** | trace search/viewer |
| OTel Collector | otel-collector:4317 (gRPC) | internal only, not published for browsing |

For Kubernetes (`infrastructure/k8s/`), see
[../infrastructure/k8s/README.md](../infrastructure/k8s/README.md) — the
same four observability services are deployed via
`infrastructure/k8s/observability.yaml`, with Grafana reachable at
**http://localhost:3000** (NodePort 30300) once `deploy-local.sh` finishes.

## How metrics are collected

Every metric is defined once in `backend/app/observability/metrics.py`
against a shared `CollectorRegistry`, imported by whichever module needs to
record it. Two things expose that registry over HTTP for Prometheus to
scrape:

- **API process**: `GET /metrics` in `backend/app/main.py`.
- **Telemetry consumer**: not an HTTP service, so it runs its own tiny
  metrics-only server (`prometheus_client.start_http_server`, port 9100 by
  default — `METRICS_PORT` env var) purely so Prometheus has something to
  scrape. See `infrastructure/observability/prometheus/prometheus.yml`
  (Compose) or the `prometheus.io/scrape` pod annotations (Kubernetes).

The simulator does **not** expose metrics (it isn't a service anything
depends on operationally) — its Kafka publishes are still counted in Kafka
consumer-side metrics on the telemetry consumer.

### Metrics reference

| Metric | Type | Labels | What it tells you |
|---|---|---|---|
| `http_requests_total` | counter | `method`, `route`, `status_code` | Request volume and error mix per endpoint |
| `http_request_duration_seconds` | histogram | `method`, `route` | Latency distribution (p50/p95/p99 in Grafana) |
| `http_requests_in_flight` | gauge | — | Concurrency / stuck-request indicator |
| `telemetry_events_received_total` | counter | — | Telemetry events read off Kafka |
| `telemetry_events_processed_total` | counter | — | Successfully persisted + published |
| `telemetry_processing_failures_total` | counter | `stage` | Failures during persist/publish |
| `telemetry_processing_duration_seconds` | histogram | — | Time to persist + publish one event |
| `kafka_messages_published_total` | counter | `topic` | Producer throughput |
| `kafka_messages_consumed_total` | counter | `topic` | Consumer throughput |
| `kafka_consumer_failures_total` | counter | `topic` | Consumer-side processing failures |
| `kafka_message_processing_duration_seconds` | histogram | `topic` | End-to-end per-message consumer time |
| `robot_commands_requested_total` | counter | `command` | Command volume by type |
| `robot_commands_processed_total` | counter | `command` | Successfully applied commands |
| `robot_commands_failed_total` | counter | `command` | Rejected/invalid commands |
| `websocket_active_connections` | gauge | — | Live dashboard connections |
| `websocket_messages_sent_total` | counter | — | Broadcast volume |
| `websocket_connection_failures_total` | counter | — | Broadcasts to stale/closed sockets |
| `fleet_robots_active` | gauge | — | Total robots known to the fleet |
| `fleet_robots_unhealthy` | gauge | — | Low battery or open high/critical incident |

**Cardinality**: `robot_id` is never a label anywhere — with a small,
fixed fleet today this wouldn't bite, but it's exactly the kind of label
that turns into an unbounded cardinality problem the moment the fleet
grows or gets dynamic IDs. Robot identity belongs in logs and trace span
attributes instead, both of which are per-event rather than
per-time-series. `command` is only added as a label after being validated
against the small fixed command set — an unrecognized value is normalized
to `"invalid"` first (see `backend/app/routes/robots.py`). The
`http_requests_total`/`http_request_duration_seconds` `route` label uses
the *matched route template* (e.g. `/robots/{robot_id}`), not the raw
request path — see `backend/app/observability/middleware.py`'s
`_route_template`.

## How tracing works

`backend/app/observability/tracing.py`'s `configure_tracing(service_name=...)`
runs once at each process's startup, before the libraries it instruments
are imported (instrumentors patch libraries at import time). It:

1. Registers a `TracerProvider` with a `service.name` resource attribute.
2. If `OTEL_EXPORTER_OTLP_ENDPOINT` is set, exports spans there over
   OTLP/gRPC via a `BatchSpanProcessor` (batched + async, so a slow or
   unreachable collector never blocks the request/consume path). If unset,
   spans are simply created and dropped — the app behaves identically
   either way, which is what lets tests run with no collector at all.
3. Auto-instruments SQLAlchemy, Redis, and kafka-python everywhere, plus
   FastAPI in the API process specifically (`instrument_fastapi`, called
   from `main.py`). `/health`, `/health/ready`, and `/metrics` are excluded
   from tracing — they're polled constantly and add noise, not insight.

**Manual spans** are added only where the auto-instrumented library spans
don't tell the full story:

- `robot.command.execute` (`backend/app/routes/robots.py`) wraps the one
  function both the HTTP command endpoint and the AI agent's write tool
  call — attributes: `robot.id`, `command.type`, `robot.new_status`.
- `telemetry.process` (`backend/app/consumers/telemetry_consumer.py`)
  wraps persist-then-publish for one telemetry event — attributes:
  `robot.id`, `messaging.system`, `messaging.destination`.
- `websocket.broadcast_telemetry` (`backend/app/websocket/redis_bridge.py`)
  wraps one fan-out to all connected dashboard clients.

No span attribute ever carries a JWT, password, or API key — attributes
are limited to IDs, command/status strings, and counts.

### Trace propagation across Kafka

`opentelemetry-instrumentation-kafka-python` injects W3C trace-context into
Kafka message headers on `producer.send()` and extracts it on the
consumer's `__next__` — so the simulator's `send` span and the telemetry
consumer's `receive` span land in the same trace automatically. Its own
consumer span, however, only stays "current" *inside* the library's
`__next__` wrapper; by the time our `for message in consumer:` loop body
runs, that span's context is already gone. To keep `telemetry.process`
(and everything nested under it — the Postgres insert, the Redis publish)
in the *same* trace rather than starting a new, disconnected one, the
consumer re-extracts context from `message.headers` itself before starting
that span (see `_process()`'s docstring in `telemetry_consumer.py` for the
full explanation). The result is one continuous trace:

```
robot-fleet-simulator: robot.telemetry send
  └─ robot-fleet-telemetry-consumer: robot.telemetry receive
       └─ telemetry.process
            ├─ connect / INSERT robot_fleet   (Postgres)
            └─ connect / PUBLISH              (Redis pub/sub)
```

The robot command flow produces a similarly complete trace without any
special-casing, since it's a single process (no Kafka hop today — see
Limitations):

```
robot-fleet-api: POST /robots/{robot_id}/command
  └─ robot.command.execute
       ├─ SELECT / UPDATE robot_fleet   (Postgres)
       └─ connect / DEL                 (Redis cache invalidation)
```

## How structured logging works

`backend/app/observability/logging.py`'s `configure_logging()` installs a
`JSONFormatter` on the root logger — called once per process, before
anything else is imported (so even startup-time log lines are JSON). It
doesn't change *what* gets logged, just *how* it's rendered: existing call
sites already followed a `logger.info("dotted.event.name", extra={...})`
convention (see `backend/app/routes/agent.py`, `incidents.py`, etc.), which
maps directly onto JSON fields.

Every log record automatically gets, with no per-call-site work required:

- `timestamp`, `level`, `service`, `logger`, `event` (the message string)
- `trace_id` / `span_id`, read from the currently active OTel span if one
  exists — this is what lets you jump from a log line straight to its
  trace in Jaeger.
- `request_id`, read from a `ContextVar` set by
  `RequestContextMiddleware` for the duration of one HTTP request (also
  returned to the client as an `X-Request-ID` response header).

Anything passed via `extra={...}` becomes its own JSON field (e.g.
`robot_id`, `command`, `duration_ms`).

Example, generated by an actual `POST /robots/R002/command` request:

```json
{"timestamp": "2026-09-18T22:01:59.317697Z", "level": "INFO", "service": "robot-fleet-api",
 "logger": "backend.app.http", "event": "http.request", "request_id": "783850e6-...",
 "trace_id": "ec8d63f12d0fb9c08cef84338c8aed7d", "span_id": "4d1c806a49e4c7ae",
 "http_method": "POST", "http_route": "/robots/{robot_id}/command",
 "http_status_code": 200, "duration_ms": 11.43}
```

**Never logged**: passwords, JWTs, API keys, or DB credentials. Nothing in
this codebase's `extra={}` calls includes those; keep it that way for new
call sites — they aren't filtered out mechanically, so this is a
convention, not a guarantee enforced in code.

## Correlation — pivoting from a metric to a trace to a log

1. **Grafana**: a panel shows a spike — e.g. "Telemetry Processing Latency
   (p95)" climbing.
2. **Jaeger**: search `robot-fleet-telemetry-consumer` for
   `telemetry.process` spans around that time window; find the slow one
   and see which child span (Postgres insert vs. Redis publish) actually
   took the time.
3. **Logs**: copy that trace's ID (shown in Jaeger's trace header), then
   `docker logs robot-fleet-telemetry-consumer | grep <trace_id>` (or
   `kubectl logs`) to see the exact `telemetry.processed` /
   `telemetry.process_failed` log line — with `robot_id`, `duration_ms`,
   and any exception detail — for that specific event.

The same flow works for an HTTP-triggered spike: Grafana's API latency
panel → Jaeger's `POST /robots/{robot_id}/command` trace → the
`request_id`/`trace_id` on that trace's `http.request` log line.

## Environment variables

| Variable | Default | Purpose |
|---|---|---|
| `OTEL_EXPORTER_OTLP_ENDPOINT` | unset (tracing no-ops) | Collector address, e.g. `http://otel-collector:4317` |
| `OTEL_SERVICE_NAME` | `robot-fleet-backend` | Per-process service name in traces/logs |
| `LOG_LEVEL` | `INFO` | Python logging level |
| `METRICS_PORT` | `9100` | Telemetry consumer's standalone metrics server port |
| `FLEET_UNHEALTHY_BATTERY_THRESHOLD` | `15` | Battery % below which a robot counts as unhealthy |
| `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` | `admin` / `admin` | Grafana login (Compose only — set these in your shell before `docker compose up` to change them) |

All are optional; the app behaves the same with none of them set (JSON
logs at INFO, tracing initialized but exporting nowhere).

## Verifying it's working

**Metrics / Prometheus**

```bash
curl -s http://localhost:8000/metrics | grep http_requests_total
open http://localhost:9090/targets   # all targets should show "UP"
```

**Grafana**

```bash
open http://localhost:3000   # admin / admin
# "Robot Fleet Platform" dashboard should already exist under the
# "Robot Fleet" folder — Dashboards → Robot Fleet → Robot Fleet Platform.
# Panels should show live data within ~30s of the stack starting.
```

**Tracing / Jaeger**

```bash
# Generate some traffic first:
curl -s -X POST http://localhost:8000/auth/login -d 'username=viewer1&password=viewer123'
open http://localhost:16686
# Service dropdown should list robot-fleet-api, robot-fleet-telemetry-consumer,
# robot-fleet-simulator. Search robot-fleet-telemetry-consumer for a
# "telemetry.process" trace — it should show spans from both the simulator
# and the consumer under one trace ID.
```

**Structured logging**

```bash
docker logs robot-fleet-backend --tail 20   # every line should be one JSON object
```

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| Prometheus target shows `DOWN` | Backend/consumer not up yet, or wrong port | Check `docker compose ps`; confirm the container's `/metrics` responds from inside the network (`docker exec robot-fleet-prometheus wget -qO- http://backend:8000/metrics`) |
| Grafana panels empty | Datasource not provisioned, or no traffic yet | Check Settings → Data Sources → Prometheus test button; generate some HTTP/telemetry traffic |
| No traces in Jaeger | `OTEL_EXPORTER_OTLP_ENDPOINT` unset, or collector unreachable | Confirm the env var is set on the process (`docker exec robot-fleet-backend env \| grep OTEL`); check `docker logs robot-fleet-otel-collector` |
| A trace only has spans from one service | Expected for Redis pub/sub → WebSocket (see Limitations) — pub/sub doesn't carry trace context | Not a bug; correlate via `robot_id`/timestamp instead for that specific hop |
| Logs aren't JSON | `configure_logging()` not called before other imports in a new entrypoint | Call it first thing, same pattern as `main.py`/`telemetry_consumer.py`/`simulator/run.py` |
| App fails to start without a collector | It shouldn't — tracing initialization is wrapped in try/except and no-ops without an endpoint | If it does, check `docker logs` for a `tracing.configure_failed` line and file it as a bug |

## Limitations and recommended follow-up

- **Robot commands don't flow through Kafka today.** The existing
  architecture applies commands directly (HTTP → Postgres/Redis — see
  `backend/app/routes/robots.py`); there's no command-topic
  producer/consumer to trace across a Kafka hop the way telemetry does.
  The command trace is real and complete for what exists (HTTP → command
  execution → DB/cache), but doesn't extend into the simulator today. If a
  command topic is added later, propagate context onto it the same way
  `telemetry_consumer.py` does for the telemetry topic.
- **Redis pub/sub does not carry trace context.** Unlike the Kafka hop,
  `redis_client.publish()`/`pubsub.listen()` have no header mechanism this
  codebase uses for context propagation, so `websocket.broadcast_telemetry`
  is a new trace rather than a continuation of the telemetry-processing
  trace. It's still attributed with `robot.id`, so cross-referencing by
  robot + timestamp is possible; a true single trace would need a custom
  context-carrying payload over pub/sub.
- **No alerting rules configured.** Prometheus/Grafana here are for
  interactive dashboards, not paging — adding Alertmanager + rules (e.g.
  error-rate or telemetry-processing-latency thresholds) would be a
  reasonable next step for a real production deployment.
- **No log aggregation backend.** Logs are structured JSON to stdout,
  correlatable by `trace_id`, but there's no Loki/ELK-style central log
  store wired up — `docker logs` / `kubectl logs` plus `grep` is the
  current workflow. Loki has a Grafana datasource that would slot in
  naturally if centralized log search becomes worth the operational cost.
- **Simulator has no metrics endpoint.** It's not depended on by anything
  operationally (it's a demo data generator — see its own comment in
  `infrastructure/k8s/simulator.yaml`), so it wasn't worth adding a second
  metrics HTTP server for. Its Kafka publishes are still visible via the
  telemetry consumer's `kafka_messages_consumed_total`.
