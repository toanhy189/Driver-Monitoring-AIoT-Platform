from typing import Literal

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file="../../.env",
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Drowsiness Detection System"

    FASTAPI_ENV: Literal["development", "production"] = "development"

    API_V1_STR: str = "/api/v1"

    DATABASE_URL: PostgresDsn

    SECRET_KEY: str

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    FRONTEND_HOST: str = "http://localhost:5173"


settings = Settings()