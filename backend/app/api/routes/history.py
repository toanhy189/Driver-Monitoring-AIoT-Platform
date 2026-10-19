from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from app.api.deps import require_viewer
from app.api.routes.commands import _public as command_public
from app.api.routes.alerts import _public as alert_public
from app.core.db import get_session
from app.models.ai_event import AiEvent
from app.models.alert import Alert
from app.models.command import Command
from app.models.telemetry import Telemetry
from app.models.user import User
from app.schemas.history import Page, TelemetryPoint, TimelineItem, MetricsResponse
from app.services.access import assigned_device
from app.services.time_utils import as_utc


router = APIRouter(tags=["history"])


@dataclass
class Window:
    start: datetime
    end: datetime
    model_version: str | None
    limit: int
    offset: int
    order: str


def history_window(
    start: Annotated[datetime | None, Query(alias="from")] = None,
    end: Annotated[datetime | None, Query(alias="to")] = None,
    model_version: Annotated[str | None, Query(min_length=1, max_length=80)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
    offset: Annotated[int, Query(ge=0, le=10000)] = 0,
    order: Literal["asc", "desc"] = "desc",
) -> Window:
    for value in (start, end):
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise HTTPException(status_code=422, detail="from/to must include a UTC offset")
    end = (end or datetime.now(timezone.utc)).astimezone(timezone.utc).replace(tzinfo=None)
    start = start.astimezone(timezone.utc).replace(tzinfo=None) if start else end - timedelta(days=1)
    if start >= end or end - start > timedelta(days=31):
        raise HTTPException(status_code=422, detail="Expected from < to with a range of at most 31 days")
    return Window(start, end, model_version, limit, offset, order)


def page(items, window):
    return {"items": items[:window.limit], "limit": window.limit,
            "offset": window.offset, "has_more": len(items) > window.limit}


def telemetry_query(device_id, window):
    query = select(Telemetry).where(Telemetry.device_id == device_id,
        Telemetry.recorded_at >= window.start, Telemetry.recorded_at < window.end)
    if window.model_version:
        query = query.where(Telemetry.model_version == window.model_version)
    return query


def command_query(device_id, window):
    query = select(Command).where(Command.device_id == device_id,
        Command.created_at >= window.start, Command.created_at < window.end)
    if window.model_version:
        query = query.join(Alert, Alert.id == Command.alert_id).join(AiEvent, AiEvent.event_id == Alert.source_event_id) \
                     .where(AiEvent.model_version == window.model_version)
    return query


def alert_query(device_id, window):
    query = select(Alert).where(Alert.device_id == device_id,
        Alert.created_at >= window.start, Alert.created_at < window.end)
    if window.model_version:
        query = query.join(AiEvent, AiEvent.event_id == Alert.source_event_id).where(AiEvent.model_version == window.model_version)
    return query


@router.get("/devices/{device_id}/telemetry/history", response_model=Page[TelemetryPoint])
def telemetry_history(device_id: int, window: Window = Depends(history_window),
                      current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    assigned_device(session, current_user.id, device_id)
    ordering = (Telemetry.recorded_at.asc(), Telemetry.id.asc()) if window.order == "asc" else \
               (Telemetry.recorded_at.desc(), Telemetry.id.desc())
    rows = session.exec(telemetry_query(device_id, window).order_by(*ordering)
                        .offset(window.offset).limit(window.limit + 1)).all()
    items = [{**row.model_dump(), "recorded_at": as_utc(row.recorded_at),
              "received_at": as_utc(row.received_at)} for row in rows]
    return page(items, window)


@router.get("/devices/{device_id}/history", response_model=Page[dict])
def command_history(device_id: int, window: Window = Depends(history_window),
                    current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    assigned_device(session, current_user.id, device_id)
    ordering = (Command.created_at.asc(), Command.id.asc()) if window.order == "asc" else \
               (Command.created_at.desc(), Command.id.desc())
    rows = session.exec(command_query(device_id, window).order_by(*ordering)
                        .offset(window.offset).limit(window.limit + 1)).all()
    return page([command_public(session, row) for row in rows], window)


@router.get("/devices/{device_id}/timeline", response_model=Page[TimelineItem])
def timeline(device_id: int, window: Window = Depends(history_window),
             current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    assigned_device(session, current_user.id, device_id)
    count = window.offset + window.limit + 1
    ascending = window.order == "asc"
    events_query = select(AiEvent).where(AiEvent.device_id == device_id,
        AiEvent.occurred_at >= window.start, AiEvent.occurred_at < window.end)
    if window.model_version:
        events_query = events_query.where(AiEvent.model_version == window.model_version)
    events = session.exec(events_query.order_by(AiEvent.occurred_at.asc() if ascending else AiEvent.occurred_at.desc(),
        AiEvent.id.asc() if ascending else AiEvent.id.desc()).limit(count)).all()
    alerts = session.exec(alert_query(device_id, window).order_by(Alert.created_at.asc() if ascending else Alert.created_at.desc(),
        Alert.id.asc() if ascending else Alert.id.desc()).limit(count)).all()
    commands = session.exec(command_query(device_id, window).order_by(Command.created_at.asc() if ascending else Command.created_at.desc(),
        Command.id.asc() if ascending else Command.id.desc()).limit(count)).all()
    items = [{"kind": "event", "id": event.id, "device_id": device_id,
        "timestamp": as_utc(event.occurred_at), "event_id": event.event_id,
        "data": {"event_type": event.event_type, "state": event.state, "outcome": event.outcome,
                 "model_version": event.model_version, "received_at": as_utc(event.received_at)}} for event in events]
    items += [{"kind": "alert", "id": alert.id, "device_id": device_id,
        "timestamp": as_utc(alert.created_at), "event_id": alert.source_event_id, "alert_id": alert.id,
        "data": alert_public(session, alert, current_user.id)} for alert in alerts]
    items += [{"kind": "command", "id": command.id, "device_id": device_id,
        "timestamp": as_utc(command.created_at), "alert_id": command.alert_id,
        "request_id": command.request_id, "data": command_public(session, command)} for command in commands]
    items.sort(key=lambda item: (item["timestamp"], item["kind"], item["id"]), reverse=not ascending)
    return page(items[window.offset:], window)


@router.get("/devices/{device_id}/metrics", response_model=MetricsResponse)
def metrics(device_id: int, window: Window = Depends(history_window),
            current_user: User = Depends(require_viewer), session: Session = Depends(get_session)):
    assigned_device(session, current_user.id, device_id)
    t = telemetry_query(device_id, window).subquery()
    c = command_query(device_id, window).subquery()
    a = alert_query(device_id, window).subquery()
    count, avg_ear, avg_perclos = session.exec(select(func.count(), func.avg(t.c.ear), func.avg(t.c.perclos)).select_from(t)).one()
    states = dict(session.exec(select(t.c.driver_state, func.count()).select_from(t).group_by(t.c.driver_state)).all())
    command_states = dict(session.exec(select(c.c.status, func.count()).select_from(c).group_by(c.c.status)).all())
    severities = dict(session.exec(select(a.c.severity, func.count()).select_from(a).group_by(a.c.severity)).all())
    avg_http, p95_http = session.exec(select(func.avg(c.c.http_duration_ms),
        func.percentile_cont(0.95).within_group(c.c.http_duration_ms)).select_from(c)).one()
    completed_ms = func.extract("epoch", c.c.completed_ack_at - c.c.created_at) * 1000
    avg_completed, p95_completed = session.exec(select(func.avg(completed_ms),
        func.percentile_cont(0.95).within_group(completed_ms)).select_from(c)).one()
    return {"device_id": device_id, "start": as_utc(window.start), "end": as_utc(window.end),
        "model_version": window.model_version,
        "telemetry": {"count": count, "avg_ear": avg_ear, "avg_perclos": avg_perclos,
                      "by_state": {str(k): v for k, v in states.items()}},
        "alerts": {"count": sum(severities.values()), "by_severity": {str(k): v for k, v in severities.items()}},
        "commands": {"count": sum(command_states.values()), "by_status": {str(k): v for k, v in command_states.items()}},
        "latency": {"clock": "backend_utc", "http_avg_ms": avg_http, "http_p95_ms": p95_http,
                    "completed_avg_ms": avg_completed, "completed_p95_ms": p95_completed}}
