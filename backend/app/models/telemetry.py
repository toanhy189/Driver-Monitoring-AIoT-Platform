from datetime import datetime
from sqlmodel import Field, SQLModel

class Telemetry(SQLModel, table=True):
    __tablename__ = "telemetry"

    id: int | None = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="devices.id")
    recorded_at: datetime = Field(default_factory=datetime.now)

    ear: float | None = None
    perclos: float | None = None

    angle_x: float | None = None
    angle_y: float | None = None
    angle_z: float | None = None

    confidence: float | None = None