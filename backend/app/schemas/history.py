from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel


T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    limit: int
    offset: int
    has_more: bool


class TelemetryPoint(BaseModel):
    id: int
    device_id: int
    recorded_at: datetime
    received_at: datetime | None
    ear: float | None
    perclos: float | None
    driver_state: str | None
    face_detected: bool | None
    head_pose: dict | None
    angle_x: float | None
    angle_y: float | None
    angle_z: float | None
    confidence: float | None
    model_version: str | None


class TimelineItem(BaseModel):
    kind: str
    id: int
    device_id: int
    timestamp: datetime
    event_id: str | None = None
    alert_id: int | None = None
    request_id: str | None = None
    data: dict


class MetricsResponse(BaseModel):
    device_id: int
    start: datetime
    end: datetime
    model_version: str | None
    telemetry: dict
    alerts: dict
    commands: dict
    latency: dict
