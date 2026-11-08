from sqlalchemy import update
from sqlmodel import Session, select

from app.core.config import settings
from app.models.ai_event import AiEvent
from app.models.video import AiVideo
from app.models.alert import Alert
from app.services.time_utils import as_utc

THRESHOLD_TYPES = {"DROWSY_THRESHOLD_REACHED", "DISTRACTED_THRESHOLD_REACHED"}


def link_event(session: Session, event: AiEvent) -> None:
    """Gọi ngay sau session.flush() của AiEvent mới, cùng transaction với receipt."""
    if event.event_type == "STATE_CHANGED":
        # video đã đến trước event
        session.execute(update(AiVideo).where(
            AiVideo.device_id == event.device_id,
            AiVideo.message_id == event.event_id,
            AiVideo.event_id.is_(None)).values(event_id=event.id))
        # threshold đã đến trước STATE_CHANGED
        session.execute(update(AiEvent).where(
            AiEvent.device_id == event.device_id,
            AiEvent.segment_message_id == event.event_id,
            AiEvent.segment_event_id.is_(None)).values(segment_event_id=event.id))
    if event.event_type in THRESHOLD_TYPES and event.segment_message_id:
        segment_id = session.exec(select(AiEvent.id).where(
            AiEvent.device_id == event.device_id,
            AiEvent.event_id == event.segment_message_id,
            AiEvent.event_type == "STATE_CHANGED")).first()
        if segment_id:
            event.segment_event_id = segment_id
            session.add(event)


def video_for_alert(session: Session, alert: Alert) -> AiVideo | None:
    if alert.event_id is None:
        return None
    return session.exec(
        select(AiVideo).join(AiEvent, AiEvent.segment_event_id == AiVideo.event_id)
        .where(AiEvent.id == alert.event_id)).first()


def video_summary(video: AiVideo) -> dict:
    return {"video_id": video.id, "device_id": video.device_id, "message_id": video.message_id,
            "state": video.state, "size_bytes": video.size_bytes,
            "created_at": as_utc(video.created_at),
            "content_url": f"{settings.API_STR}/videos/{video.id}/content"}