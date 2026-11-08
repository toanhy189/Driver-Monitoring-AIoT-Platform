from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import logging
from sqlmodel import Session, select

from app.api.deps import require_viewer
from app.core.config import settings
from app.core.db import get_session
from app.models.ai_event import AiEvent
from app.models.device import Device
from app.models.user import User
from app.models.video import AiVideo
from app.services.access import assigned_device
from app.services.audit_service import log_action
from app.services.device_auth import verify_mqtt_login
from app.services.time_utils import as_utc
from app.services.video_storage import store_video, video_path

router = APIRouter(tags=["videos"])
logger = logging.getLogger(__name__)
device_basic = HTTPBasic(scheme_name="VisionNodeCredentials", auto_error=False)


def _public(session: Session, video: AiVideo) -> dict:
    event = session.exec(select(AiEvent).where(AiEvent.event_id == video.message_id,
                                               AiEvent.device_id == video.device_id)).first()
    return {"video_id": video.id, "device_id": video.device_id, "message_id": video.message_id,
            "state": video.state, "size_bytes": video.size_bytes, "created_at": as_utc(video.created_at),
            "event_received": event is not None,
            "content_url": f"{settings.API_STR}/videos/{video.id}/content"}


def upload_device(
    device_code: Annotated[str, Form(min_length=1, max_length=100)],
    credentials: Annotated[HTTPBasicCredentials | None, Depends(device_basic)],
    session: Session = Depends(get_session),
) -> Device:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Device credentials required",
                            headers={"WWW-Authenticate": "Basic"})
    device = session.exec(select(Device).where(Device.device_code == device_code)).first()
    if device is None:
        raise HTTPException(status_code=404, detail="Vision Node not registered")
    expected = device.mqtt_username or (
        settings.AI_MQTT_USERNAME if device_code == settings.AI_DEVICE_CODE else device_code)
    if credentials.username != expected or credentials.username in {settings.MQTT_USERNAME, settings.MQTT_ADMIN_USERNAME}:
        raise HTTPException(status_code=403, detail="Credentials do not belong to this Vision Node")
    if device.device_type != "VISION_NODE" or device.lifecycle_state != "ACTIVE":
        raise HTTPException(status_code=409, detail="An active Vision Node is required")
    verify_mqtt_login(credentials.username, credentials.password)
    return device


@router.post("/videos/upload", status_code=201)
def upload_video(
    response: Response,
    file: Annotated[UploadFile, File()],
    state: Annotated[Literal["ATTENTIVE", "DISTRACTED", "DROWSY", "UNKNOWN"], Form()],
    message_id: Annotated[str, Form(min_length=1, max_length=80)],
    device: Device = Depends(upload_device),
    session: Session = Depends(get_session),
):
    video, created = store_video(session, device, file, state, message_id)
    response.status_code = 201 if created else 200
    response.headers["Cache-Control"] = "no-store"
    # Upload video truoc day khong co log; chi ghi device va ket qua, khong ghi noi dung.
    logger.info(
        "Video upload stored",
        extra={
            "event": "video_upload_stored",
            "device_code": device.device_code,
            "result": "created" if created else "duplicate",
        },
    )
    return {**_public(session, video), "status": "SAVED", "duplicate": not created}


@router.get("/devices/{device_id}/videos")
def list_videos(device_id: int, limit: int = Query(default=20, ge=1, le=100),
                offset: int = Query(default=0, ge=0, le=100000),
                message_id: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
                current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    assigned_device(session, current_user, device_id)
    query = select(AiVideo).where(AiVideo.device_id == device_id)
    if message_id:
        query = query.where(AiVideo.message_id == message_id)
    rows = session.exec(query.order_by(AiVideo.created_at.desc(), AiVideo.id.desc())
                        .offset(offset).limit(limit)).all()
    return [_public(session, row) for row in rows]


@router.get("/videos/{video_id}/content")
def download_video(video_id: int, current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    video = session.get(AiVideo, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    assigned_device(session, current_user, video.device_id)
    path = video_path(video)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    # Download truoc day khong audit; ghi sau khi assignment va file deu hop le.
    log_action(
        session, current_user.id, "DOWNLOAD_VIDEO", "AiVideo", str(video.id),
        {"video_id": video.id, "size_bytes": video.size_bytes},
    )
    session.commit()
    return FileResponse(path, media_type="video/mp4", filename=f"video-{video.id}.mp4",
                        headers={"Cache-Control": "private, no-store"})


@router.get("/devices/{device_id}/events/{event_id}/video")
def event_video(device_id: int, event_id: str,
                current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    assigned_device(session, current_user, device_id)
    event = session.exec(select(AiEvent).where(AiEvent.event_id == event_id,
                                               AiEvent.device_id == device_id)).first()
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found")
    message_id = (event.payload.get("clip_message_id") or event.payload.get("episode_start_event_id")
                  or (event.event_id if event.event_type == "STATE_CHANGED" else None))
    video = session.exec(select(AiVideo).where(AiVideo.device_id == device_id,
                                               AiVideo.message_id == message_id)).first() if message_id else None
    return {"event_id": event_id, "episode_id": event.payload.get("episode_id"),
            "clip_message_id": message_id,
            "status": ("AVAILABLE" if video_path(video).is_file() else "MISSING") if video else "PENDING_OR_UNAVAILABLE",
            "video": _public(session, video) if video else None}
