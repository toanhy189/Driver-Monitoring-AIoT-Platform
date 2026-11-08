from datetime import datetime, timezone
from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: int | None = Field(
        default=None,
        primary_key=True,
    )

    device_id: int = Field(foreign_key="devices.id")
    event_id: int | None = Field(default=None, foreign_key="ai_events.id", index=True)
    
    alert_type: str
    description: str | None = None
    
    # Status can be NEW, ACKNOWLEDGED, RESOLVED
    status: str = "NEW"

    created_at: NaiveDatetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    severity: str | None = None
    source_event_id: str | None = None
    resolved_at: NaiveDatetime | None = None   # cột đã có trong SQL
