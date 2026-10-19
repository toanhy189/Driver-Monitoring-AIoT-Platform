from datetime import datetime, timezone

from sqlalchemy import Column, JSON
from pydantic import NaiveDatetime
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

    created_at: NaiveDatetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )

    executed_at: NaiveDatetime | None = None
    request_id: str | None = Field(default=None, index=True)
    action: str | None = None
    created_by_user_id: int | None = Field(default=None, foreign_key="users.id")
    ack_status: str | None = None
    error_message: str | None = None
    dispatches: dict | None = Field(default=None, sa_column=Column(JSON))
    idempotency_key: str | None = None
    request_hash: str | None = None
    http_received_at: NaiveDatetime | None = None
    http_completed_at: NaiveDatetime | None = None
    http_duration_ms: float | None = None
    mqtt_published_at: NaiveDatetime | None = None
    first_ack_at: NaiveDatetime | None = None
    completed_ack_at: NaiveDatetime | None = None
