import asyncio

from fastapi import WebSocket
from sqlmodel import Session, select

from app.core.db import engine
from app.models.user_device import UserDevice
from app.models.user import User
from app.core.config import settings


class ConnectionManager:
    def __init__(self):
        self.connections: dict[WebSocket, int] = {}
        self.loop: asyncio.AbstractEventLoop | None = None

    async def connect(self, websocket: WebSocket, user_id: int):
        if len(self.connections) >= settings.MAX_WS_CONNECTIONS:
            await websocket.close(code=1013)
            return
        await websocket.accept()
        self.loop = asyncio.get_running_loop()
        self.connections[websocket] = user_id

    def disconnect(self, websocket: WebSocket):
        self.connections.pop(websocket, None)

    async def send_to_device_users(self, event: dict):
        data = event.get("data")
        device_id = data.get("device_id") if isinstance(data, dict) else None
        if type(device_id) is not int or device_id <= 0:
            return
        with Session(engine) as session:
            user_ids = set(session.exec(
                select(UserDevice.user_id).where(
                    UserDevice.device_id == device_id,
                    UserDevice.unassigned_at.is_(None),
                ).join(User, User.id == UserDevice.user_id).where(
                    User.role.in_(["Admin", "Employee", "Customer", "ADMIN", "OPERATOR", "VIEWER"])
                )
            ).all())
        for websocket, user_id in list(self.connections.items()):
            if user_id not in user_ids:
                continue
            try:
                await websocket.send_json(event)
            except Exception:
                self.disconnect(websocket)

    def send_from_thread(self, event: dict):
        if self.loop is not None and self.loop.is_running():
            asyncio.run_coroutine_threadsafe(self.send_to_device_users(event), self.loop)


manager = ConnectionManager()
