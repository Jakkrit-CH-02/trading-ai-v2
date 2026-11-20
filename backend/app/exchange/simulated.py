"""In-memory adapter used by tests and (from Phase 2) the backtester."""

from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime

from app.exchange.base import ExchangeAdapter
from app.exchange.types import Kline, MarketEvent


class SimulatedExchangeAdapter(ExchangeAdapter):
    def __init__(self, klines: Sequence[Kline] = (), now: datetime | None = None) -> None:
        self._klines = sorted(klines, key=lambda k: k.open_time)
        self.now = now or datetime.now(UTC)
        self.events: list[MarketEvent] = []

    async def server_time(self) -> datetime:
        return self.now

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Kline]:
        out = [
            k
            for k in self._klines
            if k.symbol == symbol
            and k.interval == interval
            and (start is None or k.open_time >= start)
            and (end is None or k.open_time <= end)
        ]
        return out[:limit]

    async def stream_market(
        self, symbols: Sequence[str], intervals: Sequence[str]
    ) -> AsyncIterator[MarketEvent]:
        for e in self.events:
            yield e
