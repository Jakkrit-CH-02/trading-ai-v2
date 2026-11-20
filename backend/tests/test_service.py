from collections.abc import AsyncIterator, Sequence
from datetime import timedelta

import pytest

from app.exchange.base import ExchangeAdapter
from app.exchange.errors import ExchangeError, IPBanned, RateLimited
from app.exchange.simulated import SimulatedExchangeAdapter
from app.exchange.types import BookTicker, MarketEvent
from app.marketdata.publisher import ListPublisher, candle_payload
from app.marketdata.service import MarketDataService, StaleWatchdog
from app.marketdata.store import InMemoryCandleStore
from tests.helpers import at, make_kline


class Stop(Exception):
    """Ends run_forever in tests."""


def _service(
    adapter: ExchangeAdapter,
) -> tuple[MarketDataService, InMemoryCandleStore, ListPublisher]:
    store, pub = InMemoryCandleStore(), ListPublisher()
    svc = MarketDataService(adapter, store, pub, ["BTCUSDT"], ["1h"], backoff_base=1, backoff_max=8)
    return svc, store, pub


async def test_forming_candle_is_neither_stored_nor_published() -> None:
    svc, store, pub = _service(SimulatedExchangeAdapter())
    await svc.handle_event(make_kline(1, closed=False))
    assert not store.rows and not pub.published


async def test_closed_candle_is_stored_and_published_once() -> None:
    svc, store, pub = _service(SimulatedExchangeAdapter())
    await svc.handle_event(make_kline(1))
    await svc.handle_event(make_kline(1))  # duplicate frame, e.g. replay after reconnect
    assert len(store.rows) == 1 and len(pub.published) == 1


async def test_book_ticker_updates_state_and_watchdog_only() -> None:
    svc, store, pub = _service(SimulatedExchangeAdapter())
    px = make_kline(0).o
    tick = BookTicker("BTCUSDT", bid=px, bid_qty=px, ask=px, ask_qty=px, ts=at(0))
    await svc.handle_event(tick)
    assert svc.last_book["BTCUSDT"] is tick and not store.rows and not pub.published


class FlakyAdapter(SimulatedExchangeAdapter):
    """First connection drops after one candle; the exchange kept producing candles meanwhile."""

    def __init__(self) -> None:
        super().__init__([make_kline(i) for i in range(8)], now=at(8) + timedelta(minutes=1))
        self.connects = 0

    async def stream_market(
        self, symbols: Sequence[str], intervals: Sequence[str]
    ) -> AsyncIterator[MarketEvent]:
        self.connects += 1
        if self.connects == 1:
            yield make_kline(2)
            raise ExchangeError("connection reset")
        if self.connects == 2:
            yield make_kline(8)  # first live candle after reconnect
            raise ExchangeError("again")
        raise Stop


async def test_reconnect_backfills_missed_candles_with_backoff() -> None:
    adapter = FlakyAdapter()
    svc, store, pub = _service(adapter)
    # Pre-existing history 0..1; candles 3..7 were closed while we were disconnected.
    await store.save([make_kline(0), make_kline(1)])
    delays: list[float] = []

    async def fake_sleep(d: float) -> None:
        delays.append(d)

    with pytest.raises(Stop):
        await svc.run_forever(sleep=fake_sleep)

    # run_once() calls recover_gaps() on every connect, so 0..7 are present with no holes
    # (candle 8 arrives live, but the simulated exchange does not list it for REST).
    assert {t for (_, _, t) in store.rows} >= {at(i) for i in range(8)}
    assert delays == [1, 2]  # exponential backoff between the failed attempts
    assert make_kline(8).open_time in {k.open_time for k in pub.published}


async def test_rate_limit_waits_retry_after() -> None:
    class Limited(SimulatedExchangeAdapter):
        n = 0

        async def stream_market(
            self, symbols: Sequence[str], intervals: Sequence[str]
        ) -> AsyncIterator[MarketEvent]:
            self.n += 1
            if self.n == 1:
                raise RateLimited(42)
            raise Stop
            yield  # pragma: no cover

    svc, _, _ = _service(Limited(now=at(1)))
    delays: list[float] = []

    async def fake_sleep(d: float) -> None:
        delays.append(d)

    with pytest.raises(Stop):
        await svc.run_forever(sleep=fake_sleep)
    assert delays == [42]


async def test_ip_ban_stops_the_service() -> None:
    class Banned(SimulatedExchangeAdapter):
        async def stream_market(
            self, symbols: Sequence[str], intervals: Sequence[str]
        ) -> AsyncIterator[MarketEvent]:
            raise IPBanned(300)
            yield  # pragma: no cover

    svc, _, _ = _service(Banned(now=at(1)))
    with pytest.raises(IPBanned):
        await svc.run_forever(sleep=lambda _: None)  # type: ignore[arg-type,return-value]


def test_stale_watchdog_flags_after_threshold() -> None:
    now = [0.0]
    dog = StaleWatchdog(10.0, clock=lambda: now[0])
    now[0] = 9.9
    assert not dog.is_stale
    now[0] = 10.1
    assert dog.is_stale
    dog.touch()
    assert not dog.is_stale


def test_candle_payload_is_all_strings() -> None:
    payload = candle_payload(make_kline(1))
    assert all(isinstance(v, str) for v in payload.values())
    assert payload["open_time"] == str(int(at(1).timestamp() * 1000)) and payload["c"] == "101.5"
