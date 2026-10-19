from pathlib import Path
from typing import Literal

from pydantic import PostgresDsn, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Drowsiness Detection System"

    FASTAPI_ENV: Literal["development", "production"] = "development"

    API_STR: str = "/api"

    DATABASE_URL: PostgresDsn

    SECRET_KEY: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    FRONTEND_HOST: str = "http://localhost:5173"

    ESP32_HOST: str = ""

    MQTT_HOST: str = "localhost"
    MQTT_PORT: int = 1883
    MQTT_USERNAME: str = ""
    MQTT_PASSWORD: str = ""
    MQTT_ADMIN_USERNAME: str = "admin"
    MQTT_ADMIN_PASSWORD: str = ""
    AI_MQTT_USERNAME: str = "vision-01"
    AI_MQTT_PASSWORD: str = ""
    SQL_ECHO: bool = False
    ENABLE_MQTT_CONSUMER: bool = True
    ENABLE_BACKGROUND_TASKS: bool = True
    RULE_ENGINE_ENABLED: bool = False
    COMMAND_TIMEOUT_SECONDS: int = Field(default=30, ge=1, le=3600)
    MAX_WS_TICKETS: int = Field(default=10000, ge=1, le=100000)
    MAX_WS_CONNECTIONS: int = Field(default=500, ge=1, le=10000)
    WS_TICKET_TTL_SECONDS: int = Field(default=30, ge=1, le=300)

settings = Settings()
