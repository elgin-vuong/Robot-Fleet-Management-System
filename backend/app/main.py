from pathlib import Path

from dotenv import load_dotenv

# Must run before any other backend.app import — several modules (e.g.
# backend.app.auth's JWT_SECRET_KEY) read environment variables at import
# time, not lazily, so loading .env any later would be too late for those.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from backend.app.observability.logging import configure_logging

# Also as early as possible: every logger.* call anywhere in the app should
# render as JSON, including ones triggered by module-level code below.
configure_logging()

from backend.app.observability.tracing import configure_tracing

# Before FastAPI/SQLAlchemy/etc. are imported, so their instrumentors (which
# patch the libraries at import time) see the real, unpatched modules first.
configure_tracing(service_name="robot-fleet-api")

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from sqlalchemy import text

from backend.app.cache import redis_client
from backend.app.database import SessionLocal
from backend.app.observability.metrics import metrics_endpoint, refresh_fleet_gauges
from backend.app.observability.middleware import RequestContextMiddleware
from backend.app.observability.tracing import instrument_fastapi
from backend.app.routes.agent import router as agent_router
from backend.app.routes.auth import router as auth_router
from backend.app.routes.documents import router as documents_router
from backend.app.routes.incidents import router as incidents_router
from backend.app.routes.robots import router as robots_router
from backend.app.routes.websocket import router as websocket_router
from backend.app.websocket.redis_bridge import listen_for_telemetry

logger = logging.getLogger("backend.app.main")

# How often the fleet-health gauges (active/unhealthy robot counts) are
# recomputed from Postgres. These are cheap aggregate queries, not
# per-request work, so a background refresh loop is simpler and cheaper
# than recomputing them on every /metrics scrape.
FLEET_GAUGE_REFRESH_SECONDS = 15


@asynccontextmanager
async def lifespan(app: FastAPI):
    bridge_task = asyncio.create_task(listen_for_telemetry())
    fleet_gauge_task = asyncio.create_task(_refresh_fleet_gauges_periodically())
    logger.info("app.startup")
    yield
    bridge_task.cancel()
    fleet_gauge_task.cancel()
    logger.info("app.shutdown")


async def _refresh_fleet_gauges_periodically() -> None:
    while True:
        try:
            db = SessionLocal()
            try:
                refresh_fleet_gauges(db)
            finally:
                db.close()
        except Exception:
            logger.exception("fleet.gauges.refresh_failed")

        await asyncio.sleep(FLEET_GAUGE_REFRESH_SECONDS)


app = FastAPI(title="Robot Fleet Management API", lifespan=lifespan)
app.add_middleware(RequestContextMiddleware)
instrument_fastapi(app)


@app.get("/metrics")
def metrics():
    """Prometheus scrape endpoint. See backend/app/observability/metrics.py."""
    return metrics_endpoint()


@app.get("/health")
def health_check():
    """Liveness: process is up and serving requests. No dependency checks."""
    return {"status": "ok"}


@app.get("/health/ready")
def readiness_check():
    """Readiness: can the app actually serve traffic right now (DB + cache reachable)."""
    problems = []

    try:
        db = SessionLocal()
        try:
            db.execute(text("SELECT 1"))
        finally:
            db.close()
    except Exception as exc:
        problems.append(f"database: {exc}")

    try:
        redis_client.ping()
    except Exception as exc:
        problems.append(f"cache: {exc}")

    if problems:
        raise HTTPException(status_code=503, detail={"status": "not ready", "problems": problems})

    return {"status": "ready"}

app.include_router(agent_router)
app.include_router(auth_router)
app.include_router(documents_router)
app.include_router(incidents_router)
app.include_router(robots_router)
app.include_router(websocket_router)