from datetime import datetime
from sqlmodel import Field, SQLModel

class UserDevice(SQLModel, table=True):
    
    __tablename__ = "telemetry"

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id")
    device_id: int = Field(foreign_key="devices.id")
    assigned_at: datetime = Field(default_factory=datetime.now)
    unassigned_at: datetime | None = None