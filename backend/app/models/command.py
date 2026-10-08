from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


class Command(SQLModel, table=True):
    __tablename__ = "commands"

    id: int | None = Field(
        default=None,
        primary_key=True,
    )

    alert_id: int | None = None

    device_id: int

    command_type_id: int

    status: str = "PENDING"

    created_at: datetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    executed_at: datetime | None = None