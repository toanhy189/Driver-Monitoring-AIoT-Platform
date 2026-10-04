from datetime import datetime
from pydantic import BaseModel

class TelemetryResponse(BaseModel):
    device_id: int
    device_code: str
    model: str
    name: str | None = None
    recorded_at: datetime

    ear: float | None = None
    perclos: float | None = None

    angle_x: float | None = None
    angle_y: float | None = None
    angle_z: float | None = None

    confidence: float | None = None