from datetime import datetime, timezone

from pydantic import NaiveDatetime
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


class AiVideo(SQLModel, table=True):
    __tablename__ = "ai_videos"
    __table_args__ = (UniqueConstraint("device_id", "message_id"),)

    id: int | None = Field(default=None, primary_key=True)
    device_id: int = Field(foreign_key="devices.id", index=True)
    message_id: str = Field(max_length=80)
    state: str = Field(max_length=30)
    storage_key: str = Field(max_length=80)
    sha256: str = Field(max_length=64)
    size_bytes: int
    created_at: NaiveDatetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
