"""Firmware artifacts and durable OTA jobs, independent of actuator commands."""
from datetime import datetime, timezone
from sqlalchemy import Column, JSON, UniqueConstraint
from sqlmodel import SQLModel, Field
from pydantic import NaiveDatetime

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

class FirmwareArtifact(SQLModel, table=True):
    __tablename__ = "firmware_artifacts"
    __table_args__ = (UniqueConstraint("version", "hardware_version"),)
    id: int | None = Field(default=None, primary_key=True)
    version: str
    hardware_version: str
    sha256: str
    app_sha256: str
    size_bytes: int
    storage_key: str
    manifest: dict = Field(sa_column=Column(JSON, nullable=False))
    state: str = "DRAFT"
    notes: str = ""
    verification_error: str | None = None
    created_by: int = Field(foreign_key="users.id")
    created_at: NaiveDatetime = Field(default_factory=utcnow)

class OtaDeployment(SQLModel, table=True):
    __tablename__ = "ota_deployments"
    id: int | None = Field(default=None, primary_key=True)
    artifact_id: int = Field(foreign_key="firmware_artifacts.id")
    created_by: int = Field(foreign_key="users.id")
    created_at: NaiveDatetime = Field(default_factory=utcnow)

class OtaJob(SQLModel, table=True):
    __tablename__ = "ota_device_jobs"
    __table_args__ = (UniqueConstraint("deployment_id", "device_id"),)
    id: int | None = Field(default=None, primary_key=True)
    deployment_id: int = Field(foreign_key="ota_deployments.id", index=True)
    device_id: int = Field(foreign_key="devices.id", index=True)
    request_id: str = Field(unique=True)
    state: str = "QUEUED"
    previous_version: str | None = None
    previous_sha256: str | None = None
    installed_version: str | None = None
    installed_sha256: str | None = None
    bytes_received: int = 0
    last_sequence: int = -1
    error: str | None = None
    created_at: NaiveDatetime = Field(default_factory=utcnow)
    updated_at: NaiveDatetime = Field(default_factory=utcnow)
    expires_at: NaiveDatetime

class OtaJobEvent(SQLModel, table=True):
    __tablename__ = "ota_job_events"
    __table_args__ = (UniqueConstraint("job_id", "event_id"),)
    id: int | None = Field(default=None, primary_key=True)
    job_id: int = Field(foreign_key="ota_device_jobs.id", index=True)
    event_id: str
    state: str
    detail: str | None = None
    bytes_received: int = 0
    created_at: NaiveDatetime = Field(default_factory=utcnow)
