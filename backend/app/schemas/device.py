from datetime import datetime
from ipaddress import IPv4Address, IPv4Interface, IPv6Address, IPv6Interface
from pydantic import BaseModel, field_validator

from app.services.time_utils import as_utc


class DeviceRegisterRequest(BaseModel):
    device_code: str
    model: str
    name: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None


class DeviceStatusRequest(BaseModel):
    status: str


class DeviceResponse(BaseModel):
    id: int
    device_code: str
    model: str
    name: str | None = None
    status: str
    type: str | None = None
    lifecycle_state: str = "REGISTERED"
    firmware_version: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    last_seen: datetime | None = None
    created_at: datetime

    @classmethod
    def from_device(cls, device):
        return cls.model_validate({
            **device.model_dump(),
            "type": device.device_type,
        })

    @field_validator("ip_address", mode="before")
    @classmethod
    def serialize_ip_address(cls, value):
        # Psycopg đọc cột INET thành object IP; API trả chuỗi cho frontend.
        if isinstance(value, (IPv4Address, IPv6Address, IPv4Interface, IPv6Interface)):
            return str(value)
        return value

    @field_validator("last_seen", "created_at", mode="before")
    @classmethod
    def mark_utc(cls, value):
        return as_utc(value) if isinstance(value, datetime) else value
