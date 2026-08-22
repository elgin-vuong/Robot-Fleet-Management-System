import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
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

app.include_router(robots_router)
app.include_router(websocket_router)