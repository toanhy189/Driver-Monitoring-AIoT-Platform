from contextlib import asynccontextmanager
from threading import Thread, Event
from datetime import datetime, timezone
from time import perf_counter
import logging
from uuid import uuid4
from sqlmodel import Session
from app.core.db import engine
from app.models.command import Command

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.routes.websocket import router as websocket_router
from app.core.config import settings
from app.core.logging_config import (
    configure_logging,
    correlation_id_context,
    request_method_context,
    request_path_context,
)
from app.services.mqtt_service import start_mqtt_consumer
from app.services.background_tasks import run_background_tasks

# Log mac dinh truoc day la van ban thuong; chuyen backend va Uvicorn sang JSON.
configure_logging()
logger = logging.getLogger(__name__)

def custom_generate_unique_id(route):
    tag = route.tags[0] if route.tags else "default"
    path = route.path_format.strip("/").replace("/", "_").replace("{", "").replace("}", "")
    method = sorted(route.methods or {"GET"})[0].lower()
    return f"{tag}-{route.name}-{method}-{path}"

@asynccontextmanager
async def lifespan(app):
    from app.services.ai_readiness import database_readiness
    try:
        readiness = database_readiness()
        if not readiness["database_ready"]:
            logging.getLogger(__name__).warning("AI ingest not ready: %s; run backend/scripts/setup_ai_ingest.py", readiness)
    except Exception as error:
        logging.getLogger(__name__).warning("AI ingest readiness check failed: %s", type(error).__name__)
    stop = Event()
    threads = []
    for enabled, task in ((settings.ENABLE_MQTT_CONSUMER, start_mqtt_consumer),
                          (settings.ENABLE_BACKGROUND_TASKS, run_background_tasks)):
        if enabled:
            worker = Thread(target=task, args=(stop,), daemon=True)
            worker.start()
            threads.append(worker)
    yield
    stop.set()
    for worker in threads:
        worker.join(timeout=5)

app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_STR}/openapi.json",
    generate_unique_id_function=custom_generate_unique_id,
    lifespan=lifespan,
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


# Middleware gan correlation ID cho HTTP log/audit va giu cac header do luong cua ung dung.
@app.middleware("http")
async def record_http_duration(request, call_next):
    request_id = uuid4().hex
    context_token = correlation_id_context.set(request_id)
    method_token = request_method_context.set(request.method)
    path_token = request_path_context.set(request.url.path)
    request.state.correlation_id = request_id
    received = datetime.now(timezone.utc).replace(tzinfo=None)
    started = perf_counter()
    response = None
    try:
        if request.url.path == f"{settings.API_STR}/videos/upload" and request.method == "POST":
            length = request.headers.get("content-length")
            # Gioi han multipart truoc khi FastAPI tao UploadFile, nhu hanh vi cu.
            if length is None:
                response = JSONResponse(
                    status_code=411,
                    content={"detail": "Content-Length required for video uploads"},
                )
            elif not length.isdigit():
                response = JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
            elif int(length) > settings.AI_VIDEO_MAX_BYTES + 1048576:
                response = JSONResponse(status_code=413, content={"detail": "Video exceeds upload size limit"})
        if response is None:
            response = await call_next(request)
        duration = round((perf_counter() - started) * 1000, 3)
        response.headers["X-Response-Time-Ms"] = str(duration)
        response.headers["X-Correlation-ID"] = request_id
        command_id = getattr(request.state, "command_id", None)
        if command_id is not None:
            with Session(engine) as session:
                command = session.get(Command, command_id)
                if command:
                    command.http_received_at = received
                    command.http_completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    command.http_duration_ms = duration
                    session.add(command)
                    session.commit()
        return response
    finally:
        # Ghi mot dong ket qua cho moi request truoc khi don context de khoanh vung loi.
        logger.info(
            "HTTP request completed",
            extra={
                "event": "http_request_completed",
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code if response is not None else 500,
                "duration_ms": round((perf_counter() - started) * 1000, 3),
            },
        )
        request_path_context.reset(path_token)
        request_method_context.reset(method_token)
        correlation_id_context.reset(context_token)
