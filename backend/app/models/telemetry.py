from datetime import datetime, timezone
from sqlalchemy import Column, JSON
from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

class Telemetry(SQLModel, table=True):
    __tablename__ = "telemetry"

    id: int | None = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="devices.id")
    recorded_at: NaiveDatetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))

    ear: float | None = None
    perclos: float | None = None

    angle_x: float | None = None
    angle_y: float | None = None
    angle_z: float | None = None

    confidence: float | None = None

    driver_state: str | None = None
    face_detected: bool | None = None
    head_pose: dict | None = Field(default=None, sa_column=Column(JSON))
    model_version: str | None = None
