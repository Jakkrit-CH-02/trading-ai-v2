"""market-data service: stream closed candles from Binance into the DB and Redis.

Loop: connect -> fill any gap since the last stored candle -> consume events. On any
disconnect, wait with exponential backoff, reconnect, and fill the gap again so no closed
candle is ever missed. Rate limit (429) pauses; an IP ban (418) stops the service.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable, Sequence
from datetime import timedelta

import structlog
from websockets.exceptions import WebSocketException

from app.exchange.base import ExchangeAdapter
from app.exchange.errors import ExchangeError, IPBanned, RateLimited
from app.exchange.types import BookTicker, Kline
from app.marketdata.backfill import fill_gaps
from app.marketdata.publisher import CandlePublisher
from app.marketdata.store import CandleStore

log = structlog.get_logger()

RECOVERY_LOOKBACK = timedelta(days=2)  # how far back a reconnect re-checks for gaps


class StaleWatchdog:
    """Flags stale data when no tick has arrived for ``threshold`` seconds (SPEC 3.3)."""

    def __init__(self, threshold: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.threshold = threshold
        self._clock = clock
        self._last = clock()

    def touch(self) -> None:
        self._last = self._clock()

    @property
    def is_stale(self) -> bool:
        return self._clock() - self._last > self.threshold


class MarketDataService:
    def __init__(
        self,
        adapter: ExchangeAdapter,
        store: CandleStore,
        publisher: CandlePublisher,
        symbols: Sequence[str],
        intervals: Sequence[str],
        stale_after: float = 10.0,
        backoff_base: float = 1.0,
        backoff_max: float = 60.0,
    ) -> None:
        self._adapter = adapter
        self._store = store
        self._publisher = publisher
        self._symbols = list(symbols)
        self._intervals = list(intervals)
        self._backoff_base = backoff_base
        self._backoff_max = backoff_max
        self.watchdog = StaleWatchdog(stale_after)
        self.last_book: dict[str, BookTicker] = {}

    async def recover_gaps(self) -> None:
        now = await self._adapter.server_time()
        for symbol in self._symbols:
            for interval in self._intervals:
                await fill_gaps(
                    self._adapter, self._store, symbol, interval, now - RECOVERY_LOOKBACK
                )

    async def handle_event(self, event: Kline | BookTicker) -> None:
        self.watchdog.touch()
        if isinstance(event, BookTicker):
            self.last_book[event.symbol] = event
            return
        if not event.is_closed:
            return  # forming candle: UI-only, never persisted or published
        inserted = await self._store.save([event])
        if inserted:  # a duplicate frame after reconnect must not re-publish
            await self._publisher.publish_closed(event)

    async def run_once(self) -> None:
        """One connection lifetime. Returns when the stream ends; raises on failure."""
        await self.recover_gaps()
        async for event in self._adapter.stream_market(self._symbols, self._intervals):
            await self.handle_event(event)

    async def run_forever(self, sleep: Callable[[float], Awaitable[None]] = asyncio.sleep) -> None:
        attempt = 0
        while True:
            try:
                await self.run_once()
                attempt = 0  # clean rotation (24h limit), reconnect immediately
                continue
            except IPBanned:
                log.error("marketdata.ip_banned")
                raise  # SPEC 3.3: 418 = stop immediately
            except RateLimited as e:
                delay = e.retry_after
                log.error("marketdata.rate_limited", retry_after=delay)
            except (ExchangeError, WebSocketException, OSError, TimeoutError) as e:
                delay = min(self._backoff_base * 2**attempt, self._backoff_max)
                log.error("marketdata.disconnected", error=repr(e), retry_in=delay)
                attempt += 1
            await sleep(delay)


async def watch_stale(
    service: MarketDataService,
    on_change: Callable[[bool], Awaitable[None]],
    period: float = 1.0,
) -> None:
    """Report stale/healthy transitions so the risk engine can pause new entries."""
    stale = False
    while True:
        now_stale = service.watchdog.is_stale
        if now_stale != stale:
            stale = now_stale
            if stale:
                log.error("marketdata.stale")
            else:
                log.info("marketdata.recovered")
            await on_change(stale)
        await asyncio.sleep(period)
