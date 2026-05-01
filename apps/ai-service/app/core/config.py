from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="AI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    service_name: str = "ai-service"
    env: Literal["dev", "staging", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"

    host: str = "0.0.0.0"
    port: int = 8001

    backend_base_url: str = Field(
        default="http://backend:8000",
        description="Go backend base URL — the only source of market bars.",
    )
    backend_timeout_s: float = 10.0


@lru_cache
def get_settings() -> Settings:
    return Settings()
