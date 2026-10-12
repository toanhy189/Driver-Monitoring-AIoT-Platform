from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from sqlmodel import Session

from app.core.config import settings
from app.core.db import engine
from app.models.user import User
from app.services.websocket_manager import manager
from app.services.ws_tickets import consume_ticket


router = APIRouter(tags=["websocket"])


@router.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket):
    ticket = websocket.query_params.get("ticket", "")
    user_id = consume_ticket(ticket)
    origin = websocket.headers.get("origin")
    if user_id is None or (origin and origin != settings.FRONTEND_HOST):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    with Session(engine) as session:
        user = session.get(User, user_id)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await manager.connect(websocket, user_id)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)
