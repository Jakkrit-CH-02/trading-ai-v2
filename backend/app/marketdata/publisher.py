"""Publish closed candles to the ``candles.closed`` Redis Stream (SPEC section 5)."""

from typing import Any, Protocol

from redis.asyncio import Redis

from app.exchange.types import Kline, dt_to_ms

STREAM = "candles.closed"
MAXLEN = 10_000


def candle_payload(k: Kline) -> dict[str, str]:
    """Wire format: strings only (money is never a float on the wire)."""
    return {
        "symbol": k.symbol,
        "interval": k.interval,
        "open_time": str(dt_to_ms(k.open_time)),
        "o": str(k.o),
        "h": str(k.h),
        "l": str(k.l),
        "c": str(k.c),
        "v": str(k.v),
    }


class CandlePublisher(Protocol):
    async def publish_closed(self, kline: Kline) -> None: ...


class RedisCandlePublisher:
    def __init__(self, redis: Redis) -> None:
        self._redis = redis

    async def publish_closed(self, kline: Kline) -> None:
        if not kline.is_closed:
            raise ValueError("only closed candles may be published")
        fields: dict[Any, Any] = dict(candle_payload(kline))  # redis-py's dict is invariant
        await self._redis.xadd(STREAM, fields, maxlen=MAXLEN, approximate=True)


class ListPublisher:
    """Test double."""

    def __init__(self) -> None:
        self.published: list[Kline] = []

    async def publish_closed(self, kline: Kline) -> None:
        self.published.append(kline)
