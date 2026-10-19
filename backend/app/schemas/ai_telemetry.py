from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat, StrictBool, field_validator


class QueuedTelemetry(BaseModel):
    message_id: str = Field(min_length=1, max_length=80)
    timestamp: datetime
    driver_state: Literal["ATTENTIVE", "DROWSY", "DISTRACTED", "UNKNOWN"] | None = None
    face_detected: StrictBool | None = None
    ear: FiniteFloat | None = None
    perclos: FiniteFloat | None = None
    confidence: FiniteFloat | None = None
    head_pose: dict[str, FiniteFloat | None] | None = None
    angle_x: FiniteFloat | None = None
    angle_y: FiniteFloat | None = None
    angle_z: FiniteFloat | None = None
    model_version: str | None = Field(default=None, max_length=80)

    @field_validator("timestamp")
    @classmethod
    def timezone_required(cls, value):
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must include UTC offset")
        return value
