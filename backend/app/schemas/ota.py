from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class FirmwareManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["driver-ota-v1"]
    key_id: Literal["ota-key-v1"]
    version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
    hardware_version: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$")
    size_bytes: int = Field(ge=256, le=2097152)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    signature: str = Field(min_length=100, max_length=1024)

def signing_bytes(manifest):
    item = manifest.model_dump() if isinstance(manifest, BaseModel) else manifest
    return (f"driver-ota-v1\n{item['key_id']}\n{item['version']}\n{item['hardware_version']}\n"
            f"{item['size_bytes']}\n{item['sha256']}\n").encode("ascii")

class OtaCapabilities(BaseModel):
    protocol: Literal["driver-ota-v1"]
    supported: bool
    max_image_bytes: int = Field(ge=0, le=16777216)
    rollback_supported: bool
    signature_required: Literal[True]
    key_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    image_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    outputs_busy: bool

class DeploymentRequest(BaseModel):
    artifact_id: int = Field(gt=0)
    device_ids: list[int] = Field(min_length=1, max_length=50)
    confirmed: bool = False

class OtaStatus(BaseModel):
    protocol: Literal["driver-ota-v1"]
    device_code: str = Field(min_length=1,max_length=100)
    request_id: str = Field(min_length=1,max_length=80)
    job_id: int = Field(gt=0)
    sequence: int = Field(ge=0,le=1000000)
    state: Literal["ACCEPTED","DOWNLOADING","VERIFYING","REBOOTING","CONFIRMED","REJECTED","FAILED","ROLLED_BACK"]
    bytes_received: int = Field(default=0,ge=0,le=2097152)
    firmware_version: str | None = Field(default=None,max_length=80)
    image_sha256: str | None = Field(default=None,pattern=r"^[a-f0-9]{64}$")
    download_sha256: str | None = Field(default=None,pattern=r"^[a-f0-9]{64}$")
    error: str | None = Field(default=None,max_length=240)
