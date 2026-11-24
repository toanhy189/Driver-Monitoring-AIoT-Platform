from datetime import datetime
from typing import Literal
from ipaddress import IPv4Address, IPv4Interface, IPv6Address, IPv6Interface
from pydantic import BaseModel, Field, field_validator

from app.services.time_utils import as_utc


class DeviceRegisterRequest(BaseModel):
    device_type: Literal["VISION_NODE", "ALERT_NODE"]
    device_code: str | None = Field(default=None, min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    model: str = Field(min_length=1, max_length=100)
    name: str | None = Field(default=None, min_length=1, max_length=255)
    ip_address: str | None = None
    mac_address: str | None = None
    hardware_version: str | None = Field(default=None, min_length=1, max_length=80)

    @field_validator("device_code", "model", "name", mode="before")
    @classmethod
    def trim_registration(cls, value):
        return value.strip() if isinstance(value, str) else value


class HardwareVersionUpdate(BaseModel):
    hardware_version: str = Field(min_length=1, max_length=80)


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
    hardware_version: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None
    last_seen: datetime | None = None
    created_at: datetime
    can_delete_registration: bool = False
    delete_block_reason: str | None = None
    ota_capabilities: dict | None = None

    @classmethod
    def from_device(cls, device):
        return cls.model_validate({
            # Validate psycopg INET objects before serializing them as strings.
            **device.model_dump(exclude={"ip_address"}),
            "ip_address": device.ip_address,
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


class ProvisionResponse(DeviceResponse):
    # Chỉ POST provision trả mật khẩu để quản trị viên đưa vào thiết bị.
    mqtt_username: str
    mqtt_password: str
