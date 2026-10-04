from datetime import datetime
from pydantic import BaseModel

class DeviceResponse(BaseModel):
    id: int
    device_code: str
    model: str
    name: str
    status: str
    ip_address: str
    mac_address: str
    last_seen: datetime
    created_at: datetime