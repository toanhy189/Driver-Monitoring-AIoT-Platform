import asyncio
from fastapi import WebSocket


class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket):
        await websocket.accept()

        self.loop = asyncio.get_running_loop()
        self.active_connections.append(websocket)

        print(
            f"[WebSocket] Client connected. "
            f"Total: {len(self.active_connections)}"
        )

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

        print(
            f"[WebSocket] Client disconnected. "
            f"Total: {len(self.active_connections)}"
        )

    async def broadcast(self, data: dict):
        disconnected = []

        for websocket in self.active_connections:
            try:
                await websocket.send_json(data)
            except Exception:
                disconnected.append(websocket)

        for websocket in disconnected:
            self.disconnect(websocket)

    def broadcast_from_thread(self, data: dict):
        """
        MQTT chạy ở thread riêng nên không thể await trực tiếp.
        Hàm này chuyển broadcast vào event loop của FastAPI.
        """
        if self.loop is not None and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(
                self.broadcast(data),
                self.loop
            )


manager = ConnectionManager()