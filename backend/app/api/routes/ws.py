import jwt
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlmodel import Session

from app.core.config import settings
from app.core import security
from app.core.db import engine
from app.models.user import User

router = APIRouter(
    tags=["websocket"],
)

class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

def authenticate_ws(token: str) -> User | None:
    try:
        payload = jwt.decode(
            token,
            settings.SECRET_KEY,
            algorithms=[security.ALGORITHM],
        )
        user_id = payload.get("sub")
        if user_id is None:
            return None
            
        with Session(engine) as session:
            user = session.get(User, int(user_id))
            return user
            
    except jwt.InvalidTokenError:
        return None

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    user = authenticate_ws(token)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
        
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            # Phản hồi lại hoặc xử lý message
            await websocket.send_text(f"Đã nhận từ {user.email}: {data}")
    except WebSocketDisconnect:
        manager.disconnect(websocket)
