from datetime import datetime
from pydantic import BaseModel, field_validator

from app.services.time_utils import as_utc

class TelemetryResponse(BaseModel):
    device_id: int
    device_code: str
    model: str
    name: str | None = None
    recorded_at: datetime

    ear: float | None = None
    perclos: float | None = None
    driver_state: str | None = None   # thêm trạng thái tài xế

    angle_x: float | None = None
    angle_y: float | None = None
    angle_z: float | None = None

    confidence: float | None = None
    face_detected: bool | None = None
    head_pose: dict | None = None
    model_version: str | None = None

    @field_validator("recorded_at", mode="before")
    @classmethod
    def mark_utc(cls, value):
        return as_utc(value) if isinstance(value, datetime) else value
