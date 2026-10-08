from pydantic import BaseModel


class DeviceRegisterRequest(BaseModel):
    device_code: str
    model: str
    name: str | None = None
    ip_address: str | None = None
    mac_address: str | None = None


class DeviceStatusRequest(BaseModel):
    status: str