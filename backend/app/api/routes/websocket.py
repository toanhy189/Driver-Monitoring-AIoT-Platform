'''Đây là endpoint không xác thực:
ws://localhost:8000/ws/telemetry

Không có:
Depends(acs.get_current_user_id)

và cũng không kiểm tra JWT.
'''

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.websocket_manager import manager


router = APIRouter(tags=["websocket"])


@router.websocket("/ws/telemetry")
async def telemetry_websocket(websocket: WebSocket):
    await manager.connect(websocket)

    try:
        while True:
            # Giữ connection sống.
            # Client hiện tại không cần gửi dữ liệu.
            await websocket.receive_text()

    except WebSocketDisconnect:
        manager.disconnect(websocket)

    except Exception as e:
        print(f"[WebSocket] Error: {e}")
        manager.disconnect(websocket)