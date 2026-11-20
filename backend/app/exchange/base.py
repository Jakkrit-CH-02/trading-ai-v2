"""ExchangeAdapter: the only seam between strategy/risk code and an exchange.

Phase 1 covers market data. Order placement, user-data streams and balances are
added in Phase 3 (Risk Engine + Execution); the same interface is implemented by
live, testnet and simulated adapters so strategy code is identical everywhere.
"""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence
from datetime import datetime

from app.exchange.types import Kline, MarketEvent


class ExchangeAdapter(ABC):
    @abstractmethod
    async def server_time(self) -> datetime:
        """Exchange clock in UTC (used for drift checks)."""

    @abstractmethod
    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Kline]:
        """Closed candles only, ascending by open_time, within [start, end]."""

    @abstractmethod
    def stream_market(
        self, symbols: Sequence[str], intervals: Sequence[str]
    ) -> AsyncIterator[MarketEvent]:
        """Yield kline and bookTicker events. May raise on disconnect; caller reconnects."""

    async def aclose(self) -> None:  # noqa: B027
        """Release network resources."""
