from datetime import timedelta

import pytest

from app.exchange.simulated import SimulatedExchangeAdapter
from app.marketdata.backfill import (
    expected_open_times,
    fill_gaps,
    find_gaps,
    floor_to_interval,
    last_closed_open_time,
)
from app.marketdata.store import InMemoryCandleStore
from tests.helpers import at, make_kline


def test_find_gaps_groups_contiguous_runs() -> None:
    present = {at(i) for i in (0, 1, 4, 7, 8)}
    assert find_gaps(present, at(0), at(9), "1h") == [
        (at(2), at(3)),
        (at(5), at(6)),
        (at(9), at(9)),
    ]


def test_find_gaps_empty_when_complete() -> None:
    assert find_gaps({at(i) for i in range(5)}, at(0), at(4), "1h") == []


def test_floor_and_last_closed() -> None:
    assert floor_to_interval(at(3) + timedelta(minutes=17), "1h") == at(3)
    assert last_closed_open_time(at(3) + timedelta(minutes=17), "1h") == at(2)
    # exactly on the boundary: candle 3 just opened, so candle 2 is the last closed
    assert last_closed_open_time(at(3), "1h") == at(2)
    assert len(expected_open_times(at(0), at(23), "1h")) == 24


async def test_fill_gaps_fetches_only_what_is_missing() -> None:
    exchange_has = [make_kline(i) for i in range(10)]
    adapter = SimulatedExchangeAdapter(exchange_has, now=at(10) + timedelta(minutes=5))
    store = InMemoryCandleStore()
    await store.save([make_kline(i) for i in (0, 1, 2, 5, 9)])

    res = await fill_gaps(adapter, store, "BTCUSDT", "1h", at(0))

    assert (res.missing, res.inserted, res.unavailable) == (5, 5, 0)
    assert len(store.rows) == 10


async def test_fill_gaps_is_idempotent() -> None:
    adapter = SimulatedExchangeAdapter([make_kline(i) for i in range(6)], now=at(6))
    store = InMemoryCandleStore()
    first = await fill_gaps(adapter, store, "BTCUSDT", "1h", at(0))
    second = await fill_gaps(adapter, store, "BTCUSDT", "1h", at(0))
    assert first.inserted == 6
    assert (second.missing, second.inserted) == (0, 0)


async def test_fill_gaps_never_fetches_the_forming_candle() -> None:
    adapter = SimulatedExchangeAdapter(
        [make_kline(i) for i in range(5)], now=at(4) + timedelta(minutes=30)
    )
    store = InMemoryCandleStore()
    await fill_gaps(adapter, store, "BTCUSDT", "1h", at(0))
    assert at(4) not in {t for (_, _, t) in store.rows}  # candle 4 is still open at 04:30
    assert len(store.rows) == 4


async def test_fill_gaps_reports_data_the_exchange_does_not_have() -> None:
    adapter = SimulatedExchangeAdapter([make_kline(i) for i in range(3, 6)], now=at(6))
    store = InMemoryCandleStore()
    res = await fill_gaps(adapter, store, "BTCUSDT", "1h", at(0))
    assert (res.inserted, res.unavailable) == (3, 3)  # candles 0-2 pre-date the listing


async def test_fill_gaps_paginates() -> None:
    adapter = SimulatedExchangeAdapter(
        [make_kline(i, "15m") for i in range(2500)], now=at(2500, "15m")
    )
    store = InMemoryCandleStore()
    res = await fill_gaps(adapter, store, "BTCUSDT", "15m", at(0, "15m"))
    assert res.inserted == 2500 and res.unavailable == 0


async def test_store_refuses_forming_candles() -> None:
    with pytest.raises(ValueError, match="forming"):
        await InMemoryCandleStore().save([make_kline(0, closed=False)])
