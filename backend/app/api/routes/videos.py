from typing import Annotated, Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
import logging
from sqlmodel import Session, select

from app.api.deps import require_viewer, require_operator, require_admin
from app.core.config import settings
from app.core.db import get_session
from app.models.ai_event import AiEvent
from app.models.device import Device
from app.models.user import User
from app.models.video import AiVideo
from app.services.access import assigned_device
from app.services.audit_service import log_action
from app.services.device_auth import verify_mqtt_login
from app.services.video_storage import store_video, video_path, storage_usage
from app.services.event_links import event_clip, video_summary
from app.services.video_playback import playback

router = APIRouter(tags=["videos"])
logger = logging.getLogger(__name__)
device_basic = HTTPBasic(scheme_name="VisionNodeCredentials", auto_error=False)


def _public(session: Session, video: AiVideo) -> dict:
    return video_summary(session, video)


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
    query = select(AiVideo).where(AiVideo.device_id == device_id, AiVideo.deleted_at.is_(None))
    if message_id:
        query = query.where(AiVideo.message_id == message_id)
    rows = session.exec(query.order_by(AiVideo.created_at.desc(), AiVideo.id.desc())
                        .offset(offset).limit(limit)).all()
    return [_public(session, row) for row in rows]


@router.get("/videos/{video_id}/content")
def download_video(video_id: int, current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    video = session.get(AiVideo, video_id)
    if video is None or video.deleted_at is not None:
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
    return event_clip(session, device_id, event_id)


def _readable_video(session, user, video_id):
    video = session.get(AiVideo, video_id)
    if video is None or video.deleted_at is not None:
        raise HTTPException(status_code=404, detail="Video not found")
    assigned_device(session, user, video.device_id)
    if not video_path(video).is_file():
        raise HTTPException(status_code=404, detail="Video file not found")
    return video


@router.get("/videos/{video_id}/playback")
@router.post("/videos/{video_id}/playback")
def video_playback_status(video_id: int, request: Request, response: Response,
                          current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    video = _readable_video(session, current_user, video_id)
    state = playback.prepare(video) if request.method == "POST" else playback.status(video)
    response.headers["Cache-Control"] = "private, no-store"
    return {"video_id": video.id, **state,
            "content_url": f"{settings.API_STR}/videos/{video.id}/playback/content" if state["status"] == "READY" else None}


@router.get("/videos/{video_id}/playback/content")
def video_playback_content(video_id: int, current_user: User = Depends(require_viewer),
                           session: Session = Depends(get_session)):
    video = _readable_video(session, current_user, video_id)
    path = playback.path(video)
    if not path.is_file():
        raise HTTPException(status_code=409, detail="Browser preview is not ready")
    log_action(session, current_user.id, "VIEW_VIDEO", "AiVideo", str(video.id), {"video_id": video.id})
    session.commit()
    return FileResponse(path, media_type="video/mp4", filename=f"video-{video.id}-web.mp4",
                        headers={"Cache-Control": "private, no-store"})


@router.get("/videos/storage")
def video_storage_status(current_user: User = Depends(require_admin)):
    return storage_usage()


@router.delete("/videos/{video_id}", status_code=204)
def delete_video(video_id: int, current_user: User = Depends(require_operator), session: Session = Depends(get_session)):
    from datetime import datetime, timezone
    video = session.exec(select(AiVideo).where(AiVideo.id == video_id).with_for_update()).first()
    if video is None:
        raise HTTPException(status_code=404, detail="Video not found")
    assigned_device(session, current_user, video.device_id)
    # Keep the metadata tombstone so retrying the same upload never restores a
    # clip that a permitted user explicitly erased.
    playback.remove_files(video)
    video.deleted_at = video.deleted_at or datetime.now(timezone.utc).replace(tzinfo=None)
    session.add(video)
    log_action(session, current_user.id, "DELETE_VIDEO", "AiVideo", str(video.id), {"video_id": video.id})
    session.commit()
    return Response(status_code=204)
