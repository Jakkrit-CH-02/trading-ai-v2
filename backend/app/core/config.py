"""Application settings. Env vars override defaults; never hardcode secrets."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "dev"
    service_name: str = "api"
    database_url: str = "postgresql+asyncpg://softtrade:softtrade@localhost:5432/softtrade"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: SecretStr = SecretStr("change-me")
    # Until Gate B only testnet/demo is allowed (see CLAUDE.md).
    binance_testnet_only: bool = True


@lru_cache
def get_settings() -> Settings:
    return Settings()
