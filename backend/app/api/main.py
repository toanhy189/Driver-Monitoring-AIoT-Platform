from fastapi import APIRouter

from app.core.config import settings
from app.api.routes import users, devices

api_router = APIRouter()
api_router.include_router(users.router)
api_router.include_router(devices.router)

from fastapi import APIRouter
@api_router.get("/health")
def health():
    return {
        "status": "OK"
    }