from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from backend.app.websocket.manager import manager

router = APIRouter()


@router.websocket("/ws/robots")
async def websocket_robots(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)
