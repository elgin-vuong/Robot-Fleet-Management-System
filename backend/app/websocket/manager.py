from fastapi import WebSocket

from backend.app.observability.metrics import (
    websocket_active_connections,
    websocket_connection_failures_total,
    websocket_messages_sent_total,
)


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)
        websocket_active_connections.set(len(self.active_connections))

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)
            websocket_active_connections.set(len(self.active_connections))

    async def broadcast(self, message: dict):
        stale_connections = []

        for connection in self.active_connections:
            try:
                await connection.send_json(message)
                websocket_messages_sent_total.inc()
            except Exception:
                websocket_connection_failures_total.inc()
                stale_connections.append(connection)

        for connection in stale_connections:
            self.disconnect(connection)


manager = ConnectionManager()
