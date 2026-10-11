from datetime import datetime, timezone
from sqlalchemy import Column, JSON
from sqlmodel import Field, SQLModel

class Config(SQLModel, table=True):
    __tablename__ = "configs"

    id: int | None = Field(
        default=None,
        primary_key=True,
    )

    device_id: int = Field(unique=True)
    
    desired_config: dict | None = Field(default=None, sa_column=Column(JSON))
    applied_config: dict | None = Field(default=None, sa_column=Column(JSON))

    updated_at: datetime | None = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
