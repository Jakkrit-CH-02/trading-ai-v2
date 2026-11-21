"""Paper-vs-backtest comparison (gate 2)."""

from datetime import datetime

import pytest

from app.backtest.engine import BacktestConfig
from app.bots.paper import DEVIATION_FLOOR_R, backtest_r, compare, deviation
from app.marketdata.store import InMemoryCandleStore
from tests.synth import standard_market, to_4h
from tests.test_runtime_parity import klines

CFG = BacktestConfig(min_quote_volume_24h=0.0)  # synthetic volumes are tiny


def test_deviation_is_relative_but_never_blows_up_on_a_tiny_backtest() -> None:
    assert deviation(2.0, 2.0) == 0.0
    assert deviation(3.0, 2.0) == pytest.approx(0.5)
    assert deviation(-1.0, 2.0) == pytest.approx(1.5)
    assert deviation(0.3, 0.0) == pytest.approx(0.3 / DEVIATION_FLOOR_R)  # floor, not /0
    assert deviation(0.2, 0.1) == pytest.approx(0.1)  # compared against 1R, not 0.1R


async def store() -> tuple[InMemoryCandleStore, datetime, datetime]:
    df = standard_market()
    st = InMemoryCandleStore()
    await st.save(klines(df, "BTCUSDT", "1h") + klines(to_4h(df), "BTCUSDT", "4h"))
    return st, df.index[3300].to_pydatetime(), df.index[-1].to_pydatetime()


async def test_backtest_counts_only_trades_opened_in_the_window_and_closed_by_its_end() -> None:
    st, start, end = await store()
    r, n = await backtest_r(st, "s1", {"tp1_r": 3.0}, ["BTCUSDT"], start, end, CFG)
    assert n > 0
    r_late, n_late = await backtest_r(
        st, "s1", {"tp1_r": 3.0}, ["BTCUSDT"], end.replace(year=end.year), end, CFG
    )
    assert n_late == 0 and r_late == 0.0  # nothing opens in an empty window
    assert isinstance(r, float)


async def test_identical_results_have_zero_deviation_and_a_readable_detail() -> None:
    st, start, end = await store()
    bt, n = await backtest_r(st, "s1", {"tp1_r": 3.0}, ["BTCUSDT"], start, end, CFG)
    same = await compare(st, "s1", {"tp1_r": 3.0}, ["BTCUSDT"], start, end, bt, CFG)
    assert same.deviation == 0.0 and same.backtest_trades == n
    assert "backtest" in same.detail and "paper" in same.detail
    off = await compare(st, "s1", {"tp1_r": 3.0}, ["BTCUSDT"], start, end, bt + abs(bt), CFG)
    assert off.deviation is not None and off.deviation > 0.3


async def test_not_enough_data_is_none_not_a_pass() -> None:
    st, start, end = await store()
    # window with no closed backtest trades
    none = await compare(st, "s1", {}, ["BTCUSDT"], end, end, 0.0, CFG)
    assert none.deviation is None and "no closed trades" in none.detail
    # no candles at all for the symbol
    empty = await compare(InMemoryCandleStore(), "s1", {}, ["BTCUSDT"], start, end, 0.0, CFG)
    assert empty.deviation is None and "candles" in empty.detail
    # the grid is not run live, so it has nothing to compare
    grid = await compare(st, "s4", {}, ["BTCUSDT"], start, end, 0.0, CFG)
    assert grid.deviation is None and "not run live" in grid.detail
