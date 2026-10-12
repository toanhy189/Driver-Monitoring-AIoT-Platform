from datetime import datetime, timezone

from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import INET, MACADDR


class Device(SQLModel, table=True):
    __tablename__ = "devices"

    id: int | None = Field(
        default=None,
        primary_key=True,
    )

    device_code: str
    model: str
    name: str | None = None

    status: str = "OFFLINE"
    device_type: str | None = None
    lifecycle_state: str = "REGISTERED"
    firmware_version: str | None = None

    ip_address: str | None = Field(
        default=None,
        sa_column=Column(INET, nullable=True),
    )

    mac_address: str | None = Field(
        default=None,
        sa_column=Column(MACADDR, nullable=True),
    )

    last_seen: NaiveDatetime | None = None

    created_at: NaiveDatetime = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    mqtt_username: str | None = None
    mqtt_password: str | None = None
