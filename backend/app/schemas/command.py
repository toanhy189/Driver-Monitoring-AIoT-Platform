from typing import Literal

from pydantic import BaseModel, Field, StrictInt


class TestAlertRequest(BaseModel):
    action: Literal["TEST_ALERT"]
    buzzer_ms: StrictInt = Field(ge=1, le=10000)
    vibration_ms: StrictInt = Field(ge=1, le=10000)
    led_mode: Literal["ON", "FLASH"]


class LegacyCommandRequest(BaseModel):
    device_code: str
    command: str
    duration: StrictInt = Field(default=1000, ge=0, le=10000)
    intensity: Literal["WEAK", "MEDIUM", "STRONG", "CONSTANT"] = "MEDIUM"
