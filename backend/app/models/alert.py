from datetime import datetime, timezone
from sqlmodel import Field, SQLModel

class Alert(SQLModel, table=True):
    __tablename__ = "alerts"

    id: int | None = Field(
        default=None,
        primary_key=True,
    )

    device_id: int
    
    alert_type: str
    description: str | None = None
    
    # Status can be NEW, ACKNOWLEDGED, RESOLVED
    status: str = "NEW"

    created_at: datetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
