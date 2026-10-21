from contextlib import asynccontextmanager
from threading import Thread, Event
from datetime import datetime, timezone
from time import perf_counter
import logging
from sqlmodel import Session
from app.core.db import engine
from app.models.command import Command

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware

from app.api.main import api_router
from app.api.routes.websocket import router as websocket_router
from app.core.config import settings
from app.services.mqtt_service import start_mqtt_consumer
from app.services.background_tasks import run_background_tasks

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


@app.middleware("http")
async def record_http_duration(request, call_next):
    if request.url.path == f"{settings.API_STR}/videos/upload" and request.method == "POST":
        length = request.headers.get("content-length")
        # Bound multipart parsing/spooling too, before FastAPI constructs UploadFile.
        if length is None:
            return JSONResponse(status_code=411, content={"detail": "Content-Length required for video uploads"})
        if not length.isdigit():
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})
        if int(length) > settings.AI_VIDEO_MAX_BYTES + 1048576:
            return JSONResponse(status_code=413, content={"detail": "Video exceeds upload size limit"})
    received = datetime.now(timezone.utc).replace(tzinfo=None)
    started = perf_counter()
    response = await call_next(request)
    duration = round((perf_counter() - started) * 1000, 3)
    response.headers["X-Response-Time-Ms"] = str(duration)
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
