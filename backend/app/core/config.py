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
    # base64 32-byte key wrapping per-record data keys (API keys, TOTP secrets); see auth/crypto.py
    master_key: SecretStr = SecretStr("")
    telegram_bot_token: SecretStr = SecretStr("")
    telegram_chat_id: str = ""
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
    # AI layer (SPEC 4). Only the ai-worker service gets the key; never logged, never in a prompt.
    anthropic_api_key: SecretStr = SecretStr("")
    ai_news_model: str = "claude-haiku-5-5"
    ai_brief_model: str = "claude-sonnet-5-5"
    ai_monthly_budget_usd: float = 20.0
    ai_timeout_s: float = 20.0  # SPEC 4.2: past this the bot carries on with S_ai = 50
    news_feeds: list[str] = [
        "CoinDesk|https://www.coindesk.com/arc/outboundfeeds/rss/",
        "Cointelegraph|https://cointelegraph.com/rss",
        "Decrypt|https://decrypt.co/feed",
    ]


@lru_cache
def get_settings() -> Settings:
    return Settings()
