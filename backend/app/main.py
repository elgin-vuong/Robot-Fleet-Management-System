from pathlib import Path

from dotenv import load_dotenv

# Must run before any other backend.app import — several modules (e.g.
# backend.app.auth's JWT_SECRET_KEY) read environment variables at import
# time, not lazily, so loading .env any later would be too late for those.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from backend.app.routes.agent import router as agent_router
from backend.app.routes.auth import router as auth_router
from backend.app.routes.robots import router as robots_router
from backend.app.routes.websocket import router as websocket_router
from backend.app.websocket.redis_bridge import listen_for_telemetry


@asynccontextmanager
async def lifespan(app: FastAPI):
    bridge_task = asyncio.create_task(listen_for_telemetry())
    yield
    bridge_task.cancel()


app = FastAPI(title="Robot Fleet Management API", lifespan=lifespan)

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(agent_router)
app.include_router(auth_router)
app.include_router(robots_router)
app.include_router(websocket_router)