from fastapi import APIRouter

from app.core.config import settings
from app.api.routes import users
from app.api.routes import commands
from app.api.routes import devices
from app.api.routes import configs
from app.api.routes import alerts
from app.api.routes import ws

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(commands.router)
api_router.include_router(devices.router)
api_router.include_router(configs.router)
api_router.include_router(alerts.router)
api_router.include_router(ws.router)

from fastapi import APIRouter
@api_router.get("/health")
def health():
    return {
        "status": "OK"
    }