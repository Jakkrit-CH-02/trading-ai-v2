"""Application settings. Env vars override defaults; never hardcode secrets."""

from functools import lru_cache

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    env: str = "dev"
    service_name: str = "api"
    database_url: str = "postgresql+asyncpg://softtrade:softtrade@localhost:5432/softtrade"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: SecretStr = SecretStr("change-me")
    symbols: list[str] = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    intervals: list[str] = ["15m", "1h", "4h"]
    # Read-only public market data. Order endpoints (testnet) arrive in Phase 3.
    binance_rest_url: str = "https://data-api.binance.vision"
    binance_ws_url: str = "wss://data-stream.binance.vision"
    fng_url: str = "https://api.alternative.me/fng/"  # public Fear & Greed index
    stale_after_seconds: float = 10.0
    # Until Gate B only testnet/demo is allowed (see CLAUDE.md).
    binance_testnet_only: bool = True
    # "demo" = Binance Demo Trading (demo-api.binance.com), "testnet" = testnet.binance.vision.
    # A key only works in the environment it was created in.
    binance_trading_env: str = "demo"
    # Demo/testnet credentials (fake money only). Never logged, never sent to an LLM.
    binance_api_key: SecretStr = SecretStr("")
    binance_api_secret: SecretStr = SecretStr("")


@lru_cache
def get_settings() -> Settings:
    return Settings()
