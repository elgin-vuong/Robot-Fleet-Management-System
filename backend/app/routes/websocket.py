from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.auth import decode_access_token
from backend.app.database import SessionLocal
from backend.app.models.user import User
from backend.app.websocket.manager import manager

router = APIRouter()


def _authenticate(token: str | None) -> User | None:
    if token is None:
        return None

    try:
        payload = decode_access_token(token)
    except Exception:
        return None

    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == payload.get("sub")).first()
    finally:
        db.close()


@router.websocket("/ws/robots")
async def websocket_robots(websocket: WebSocket, token: str | None = None):
    user = _authenticate(token)

    if user is None:
        await websocket.close(code=1008)
        return

    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
