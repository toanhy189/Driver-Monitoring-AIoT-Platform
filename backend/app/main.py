from pathlib import Path

from fastapi import FastAPI
from fastapi.routing import APIRoute
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.core.config import settings
from app.api.routes.websocket import router as websocket_router

#Tương đối với backend/
FRONTEND_DIR = Path("frontend")

def custom_generate_unique_id(route):
    tag = route.tags[0] if route.tags else "default"
    return f"{tag}-{route.name}"

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_HOST],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_STR)

app.include_router(websocket_router)
''' Không cho WebSocket vào:
app.include_router(api_router, prefix=settings.API_STR)

vì như vậy endpoint sẽ thành:
/api/ws/telemetry

Trong khi frontend của đang dùng:
/ws/telemetry
'''
