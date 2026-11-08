"""Resolve event/alert clips by explicit IDs, scoped to the originating device.

Adapts the alert-video feature from feature/alert-video-link to policy v1.
No nearest-time/state inference or schema rewrite is required.
"""
from sqlmodel import Session, select

from app.core.config import settings
from app.models.ai_event import AiEvent
from app.models.video import AiVideo
from app.services.time_utils import as_utc
from app.services.video_storage import video_path


def video_summary(session: Session, video: AiVideo) -> dict:
    event = session.exec(select(AiEvent.id).where(
        AiEvent.device_id == video.device_id, AiEvent.event_id == video.message_id)).first()
    return {
        "video_id": video.id, "device_id": video.device_id,
        "message_id": video.message_id, "state": video.state,
        "size_bytes": video.size_bytes, "created_at": as_utc(video.created_at),
        "event_received": event is not None,
        "deleted_at": as_utc(video.deleted_at) if video.deleted_at else None,
        "content_url": f"{settings.API_STR}/videos/{video.id}/content",
    }


def event_clip(session: Session, device_id: int, event_id: str | None) -> dict:
    event = session.exec(select(AiEvent).where(
        AiEvent.device_id == device_id, AiEvent.event_id == event_id)).first() if event_id else None
    if event is None:
        return {"event_id": event_id, "clip_message_id": None,
                "status": "UNLINKED", "video": None}
    payload = event.payload or {}
    # A current clip ID is authoritative, even if another clip in its episode
    # has already arrived. state_event_id is the explicit legacy branch field.
    message_id = (payload.get("clip_message_id") or payload.get("state_event_id")
                  or payload.get("episode_start_event_id")
                  or (event.event_id if event.event_type == "STATE_CHANGED" else None))
    if not isinstance(message_id, str) or not message_id or len(message_id) > 80:
        message_id = None
    video = session.exec(select(AiVideo).where(
        AiVideo.device_id == device_id, AiVideo.message_id == message_id)).first() if message_id else None
    status = "PENDING_OR_UNAVAILABLE" if message_id else "UNLINKED"
    if video:
        status = "DELETED" if video.deleted_at else "AVAILABLE" if video_path(video).is_file() else "MISSING"
    return {"event_id": event.event_id, "episode_id": payload.get("episode_id"),
            "clip_message_id": message_id, "status": status,
            "video": video_summary(session, video) if video else None}
