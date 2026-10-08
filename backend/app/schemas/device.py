from datetime import datetime
from ipaddress import IPv4Address, IPv4Interface, IPv6Address, IPv6Interface
from pydantic import BaseModel, field_validator

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

    @field_validator("ip_address", mode="before")
    @classmethod
    def serialize_ip_address(cls, value):
        # Psycopg đọc cột INET thành object IP; API trả chuỗi cho frontend.
        if isinstance(value, (IPv4Address, IPv6Address, IPv4Interface, IPv6Interface)):
            return str(value)
        return value
