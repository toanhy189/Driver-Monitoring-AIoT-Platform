from datetime import datetime, timezone
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

class AuditLog(SQLModel, table=True):
    __tablename__ = "audit_logs"

    id: int | None = Field(
        default=None,
        primary_key=True,
    )

    user_id: int
    action: str
    entity_type: str | None = None
    entity_id: str | None = None
    
    details: dict | None = Field(default=None, sa_column=Column(JSON))

    created_at: datetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
