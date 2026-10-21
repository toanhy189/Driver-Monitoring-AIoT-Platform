from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from sqlmodel import Session, select

from app.api.deps import require_viewer
from app.core.config import settings
from app.core.db import get_session
from app.models.ai_event import AiEvent
from app.models.device import Device
from app.models.user import User
from app.models.video import AiVideo
from app.services.access import assigned_device
from app.services.device_auth import verify_mqtt_login
from app.services.time_utils import as_utc
from app.services.video_storage import store_video, video_path

router = APIRouter(tags=["videos"])
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
    return {**_public(session, video), "status": "SAVED", "duplicate": not created}


@router.get("/devices/{device_id}/videos")
def list_videos(device_id: int, limit: int = Query(default=20, ge=1, le=100),
                offset: int = Query(default=0, ge=0, le=100000),
                current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    assigned_device(session, current_user.id, device_id)
    rows = session.exec(select(AiVideo).where(AiVideo.device_id == device_id)
                        .order_by(AiVideo.created_at.desc(), AiVideo.id.desc()).offset(offset).limit(limit)).all()
    return [_public(session, row) for row in rows]


@router.get("/videos/{video_id}/content")
def download_video(video_id: int, current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    video = session.get(AiVideo, video_id)
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    assigned_device(session, current_user.id, video.device_id)
    path = video_path(video)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    return FileResponse(path, media_type="video/mp4", filename=f"video-{video.id}.mp4",
                        headers={"Cache-Control": "private, no-store"})
