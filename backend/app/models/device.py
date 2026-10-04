from datetime import datetime
from sqlmodel import Field, SQLModel

class Device(SQLModel, table=True):
    __tablename__ = "devices"

    id: int | None = Field(default=None, primary_key=True)
    device_code: str
    model: str
    name: str | None = None
    status: str = "OFFLINE"
    ip_address: str | None = None
    mac_address: str | None = None
    last_seen: datetime | None = None
    created_at: datetime = Field(default_factory=datetime.now)