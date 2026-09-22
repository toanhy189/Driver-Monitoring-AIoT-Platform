from fastapi import APIRouter

from app.core.config import settings
from app.api.routes import users

api_router = APIRouter()
api_router.include_router(users.router)