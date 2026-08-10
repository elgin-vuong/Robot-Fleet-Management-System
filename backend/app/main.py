from fastapi import FastAPI
from backend.app.routes.robots import router as robots_router

app = FastAPI(title="Robot Fleet Management API")

@app.get("/health")
def health_check():
    return {"status": "ok"}

app.include_router(robots_router)