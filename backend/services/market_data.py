"""Entrypoint: ``python -m services.market_data``."""

import asyncio
import contextlib

from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.exchange import BinancePublicAdapter
from app.marketdata.publisher import RedisCandlePublisher
from app.marketdata.service import MarketDataService, watch_stale
from app.marketdata.store import PgCandleStore

STALE_KEY = "marketdata:stale"


async def main() -> None:
    s = get_settings()
    configure_logging("market-data")
    engine = make_engine()
    redis: Redis = Redis.from_url(s.redis_url, decode_responses=True)
    adapter = BinancePublicAdapter(s.binance_rest_url, s.binance_ws_url)
    service = MarketDataService(
        adapter,
        PgCandleStore(make_session_factory(engine)),
        RedisCandlePublisher(redis),
        s.symbols,
        s.intervals,
        stale_after=s.stale_after_seconds,
    )

    async def flag(stale: bool) -> None:
        if stale:
            await redis.set(STALE_KEY, "1")
        else:
            await redis.delete(STALE_KEY)

    watcher = asyncio.create_task(watch_stale(service, flag))
    try:
        await service.run_forever()
    finally:
        watcher.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await watcher
        await adapter.aclose()
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
