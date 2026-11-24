from datetime import datetime, timezone
from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel


class AlertRead(SQLModel, table=True):
    __tablename__ = "alert_reads"

    alert_id: int = Field(foreign_key="alerts.id", primary_key=True)
    user_id: int = Field(foreign_key="users.id", primary_key=True)
    acknowledged_at: NaiveDatetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
