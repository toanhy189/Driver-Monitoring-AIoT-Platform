from fastapi import APIRouter, Depends

from app.api.deps import require_viewer
from app.models.user import User
from app.services.ws_tickets import TTL_SECONDS, issue_ticket


router = APIRouter(tags=["websocket"])


@router.post("/ws-ticket")
def get_ws_ticket(current_user: User = Depends(require_viewer)):
    return {"ticket": issue_ticket(current_user.id), "expires_in": TTL_SECONDS}
