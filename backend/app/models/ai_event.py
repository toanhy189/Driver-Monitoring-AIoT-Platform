from datetime import datetime, timezone

from pydantic import NaiveDatetime
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel


class AiEvent(SQLModel, table=True):
    __tablename__ = "ai_events"

    id: int | None = Field(default=None, primary_key=True)
    event_id: str = Field(unique=True, index=True, max_length=80)
    device_id: int = Field(foreign_key="devices.id", index=True)
    event_type: str
    occurred_at: NaiveDatetime
    received_at: NaiveDatetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    model_version: str | None = None
    state: str | None = None
    state_duration_ms: int | None = None
    payload_hash: str
    payload: dict = Field(sa_column=Column(JSON, nullable=False))
    outcome: str = "RECORDED"


class RuleBinding(SQLModel, table=True):
    __tablename__ = "rule_bindings"

    source_device_id: int = Field(primary_key=True, foreign_key="devices.id")
    target_device_id: int = Field(foreign_key="devices.id")
    enabled: bool = False
    policy: dict = Field(sa_column=Column(JSON, nullable=False))
    last_triggered_at: NaiveDatetime | None = None
    updated_at: NaiveDatetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
