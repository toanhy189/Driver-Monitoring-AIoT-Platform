"""Store a bounded MP4 upload and commit its metadata; retries share one device/message ID."""

import hashlib
import logging
import os
from pathlib import Path
import tempfile
from uuid import uuid4

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, select

from app.core.config import settings
from app.models.ai_event import AiEvent
from app.models.device import Device
from app.models.video import AiVideo

logger = logging.getLogger(__name__)


def video_path(video: AiVideo) -> Path:
    root = settings.AI_VIDEO_DIR.resolve()
    path = (root / video.storage_key).resolve()
    if not path.is_relative_to(root):
        raise HTTPException(status_code=404, detail="Video file not found")
    return path


def store_video(session: Session, device: Device, upload: UploadFile, state: str, message_id: str) -> tuple[AiVideo, bool]:
    if upload.content_type != "video/mp4" or not (upload.filename or "").lower().endswith(".mp4"):
        raise HTTPException(status_code=415, detail="Expected an MP4 video")
    temporary = None
    destination = None
    committed = False
    try:
        root = settings.AI_VIDEO_DIR.resolve()
        root.mkdir(parents=True, exist_ok=True)
        digest = hashlib.sha256()
        size = 0
        header = b""
        with tempfile.NamedTemporaryFile(dir=root, suffix=".part", delete=False) as output:
            temporary = Path(output.name)
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.AI_VIDEO_MAX_BYTES:
                    raise HTTPException(status_code=413, detail="Video exceeds upload size limit")
                if len(header) < 32:
                    header += chunk[:32 - len(header)]
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        # Check the ISO media container header. This endpoint does not decode/transcode video.
        if len(header) < 12 or header[4:8] != b"ftyp":
            raise HTTPException(status_code=415, detail="Invalid MP4 container header")
        # Serialize uploads per device; recheck lifecycle after the file has finished arriving.
        current = session.exec(select(Device).where(Device.id == device.id).with_for_update()
                               .execution_options(populate_existing=True)).one()
        if current.lifecycle_state != "ACTIVE" or current.device_type != "VISION_NODE":
            raise HTTPException(status_code=409, detail="An active Vision Node is required")
        event = session.exec(select(AiEvent).where(AiEvent.event_id == message_id)).first()
        if event and (event.device_id != device.id or event.event_type != "STATE_CHANGED" or event.state != state):
            raise HTTPException(status_code=409, detail="Video metadata does not match its event")
        existing = session.exec(select(AiVideo).where(AiVideo.device_id == device.id,
                                                      AiVideo.message_id == message_id)).first()
        if existing:
            if existing.sha256 != digest.hexdigest() or existing.state != state:
                raise HTTPException(status_code=409, detail="Message ID already has a different video")
            if not video_path(existing).is_file():
                raise HTTPException(status_code=503, detail="Stored video file is missing; contact the administrator")
            session.rollback()
            return existing, False
        key = uuid4().hex + ".mp4"
        destination = root / key
        os.replace(temporary, destination)
        row = AiVideo(device_id=device.id, message_id=message_id, state=state,
                      storage_key=key, sha256=digest.hexdigest(), size_bytes=size)
        session.add(row)
        session.commit()
        committed = True
        session.refresh(row)
        return row, True
    except HTTPException:
        session.rollback()
        raise
    except Exception as error:
        session.rollback()
        logger.error("Video storage failed: device=%r message_id=%r error=%s",
                     device.device_code, message_id, type(error).__name__)
        raise HTTPException(status_code=503, detail="Video could not be saved; retry with the same message_id") from None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
        if destination is not None and not committed:
            destination.unlink(missing_ok=True)
