from datetime import datetime
from pydantic import BaseModel

class DeviceResponse(BaseModel):
    id: int
    device_code: str
    model: str
    name: str | None = None
    status: str
    ip_address: str | None = None
    mac_address: str | None = None
    last_seen: datetime | None = None
    created_at: datetime