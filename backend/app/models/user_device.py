from datetime import datetime, timezone
from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

class UserDevice(SQLModel, table=True):
    
    __tablename__ = "user_devices"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    device_id: int = Field(foreign_key="devices.id")
    assigned_at: NaiveDatetime = Field(default_factory=lambda: datetime.now(timezone.utc).replace(tzinfo=None))
    unassigned_at: NaiveDatetime | None = None
