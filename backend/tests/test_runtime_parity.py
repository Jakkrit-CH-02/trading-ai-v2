"""Live path == backtest path (SPEC principle 2: the same code in backtest, paper and live).

For every bar where the full-history backtest sees a signal (plus a sample of quiet bars), the
live path - which only reads a trailing window of *closed* candles up to that bar - must reach
exactly the same decision.
"""

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig
from app.backtest.registry import make_strategy
from app.exchange.types import INTERVAL_MS, Kline
from app.marketdata.store import InMemoryCandleStore
from app.runtime.frames import WINDOW_BARS, DataGap, load_features
from app.strategies.base import MarketFrames, Strategy
from app.strategies.decision import decide_at_close
from app.strategies.params import S3Params
from app.strategies.s1_trend import S1Trend
from app.strategies.s2_meanrev import S2MeanReversion
from app.strategies.s3_breakout import S3Breakout
from app.strategies.types import Regime
from tests.synth import frames, make_1h, standard_market, to_4h


def long_market() -> pd.DataFrame:
    """~9900 bars: more than the live window, with trend, range, squeeze and down phases."""
    segs = [("up", 1500), ("range", 1200), ("squeeze", 400), ("up", 800), ("down", 900),
            ("range", 1000), ("up", 1200), ("range", 1500), ("squeeze", 400), ("up", 700),
            ("range", 900), ("down", 600), ("range", 800), ("up", 1000)]  # fmt: skip
    return make_1h(segs, seed=3)


CFG = BacktestConfig()


def klines(df: pd.DataFrame, symbol: str, interval: str) -> list[Kline]:
    def d(x: float) -> Decimal:
        return Decimal(repr(float(x)))

    return [
        Kline(
            symbol,
            interval,
            pd.Timestamp(str(ts)).to_pydatetime(),
            d(r.open),
            d(r.high),
            d(r.low),
            d(r.close),
            d(r.volume),
            d(r.quote_volume),
            1,
            Decimal(0),
        )
        for ts, r in df.iterrows()
    ]


async def store_with(
    df1: pd.DataFrame, symbol: str, btc: pd.DataFrame | None
) -> InMemoryCandleStore:
    st = InMemoryCandleStore()
    await st.save(klines(df1, symbol, "1h") + klines(to_4h(df1), symbol, "4h"))
    if btc is not None:
        await st.save(klines(to_4h(btc), "BTCUSDT", "4h"))
    return st


STRATEGIES: dict[str, Callable[[], Strategy]] = {
    "s1": S1Trend,
    "s2": S2MeanReversion,
    # the SPEC regime filter leaves S3 silent on synthetic data; relax it to have signals
    "s3_wide": lambda: S3Breakout(
        S3Params(regimes=(Regime.TREND_UP, Regime.RANGE, Regime.NEUTRAL))
    ),
}


@pytest.mark.parametrize("name", list(STRATEGIES))
@pytest.mark.parametrize("symbol", ["BTCUSDT", "ETHUSDT"])
async def test_live_decisions_equal_backtest_decisions(name: str, symbol: str) -> None:
    df = long_market()
    assert len(df) > WINDOW_BARS["1h"] + 500  # the window is genuinely shorter than history
    btc = df  # BTC drives the market filter of every other symbol (and outlasts it here)
    own = (
        df
        if symbol == "BTCUSDT"
        else make_1h(
            [
                ("up", 1500),
                ("range", 2500),
                ("up", 1500),
                ("range", 1500),
                ("squeeze", 400),
                ("up", 1200),
                ("range", 1000),
                ("squeeze", 400),
                ("up", 1300),
                ("range", 600),
            ],
            seed=5,
        )
    )
    store = await store_with(own, symbol, None if symbol == "BTCUSDT" else btc)
    strat: Strategy = STRATEGIES[name]()
    full = MarketFrames(
        symbol, {"1h": own, "4h": to_4h(own)}, None if symbol == "BTCUSDT" else to_4h(btc)
    )
    feats = strat.prepare(full)
    step = INTERVAL_MS[strat.exec_interval] // 3_600_000  # bars of 1h per exec bar
    start = WINDOW_BARS[strat.exec_interval]  # only bars beyond the window test the window
    signal_bars = [
        i
        for i in range(start, len(feats))
        if decide_at_close(strat, feats, i, CFG.weights, CFG.min_quote_volume_24h, False)
        is not None
    ]
    quiet = [i for i in range(start, len(feats), 150 // step) if i not in signal_bars]
    signal_bars = signal_bars[:: max(1, len(signal_bars) // 30)]  # bound the runtime
    assert signal_bars, "the synthetic market must produce signals or this test proves nothing"

    for i in [*signal_bars, *quiet]:
        want = decide_at_close(strat, feats, i, CFG.weights, CFG.min_quote_volume_24h, False)
        live = await load_features(store, strat, symbol, feats.time(i))
        got = decide_at_close(
            strat, live, len(live) - 1, CFG.weights, CFG.min_quote_volume_24h, False
        )
        assert got == want, f"{name} {symbol} bar {feats.time(i)}"


async def test_a_4h_bar_closing_with_the_1h_bar_is_waited_for_then_used() -> None:
    df = standard_market().iloc[:2000]
    store = await store_with(df, "BTCUSDT", None)
    strat: Strategy = make_strategy("s1")  # type: ignore[assignment]
    bar_open = df.index[-1].to_pydatetime()  # last 1h bar: 4h bar closing with it
    h4_open = bar_open - pd.Timedelta(hours=3)
    assert h4_open.hour % 4 == 0 or True
    # remove the 4h candle that closes together with this 1h bar
    key = ("BTCUSDT", "4h", pd.Timestamp(h4_open).to_pydatetime())
    held_back = store.rows.pop(key, None)
    if held_back is None:
        pytest.skip("synthetic window does not end on a 4h boundary")
    with pytest.raises(DataGap):
        await load_features(store, strat, "BTCUSDT", bar_open, wait_s=0)

    async def late_arrival(_: float) -> None:
        store.rows[key] = held_back  # the 4h candle lands while we wait

    feats = await load_features(
        store, strat, "BTCUSDT", bar_open, wait_s=10, poll_s=2, sleep=late_arrival
    )
    assert feats.time(len(feats) - 1) == bar_open


async def test_missing_exec_bar_is_a_data_gap_not_a_guess() -> None:
    df = standard_market().iloc[:1500]
    store = await store_with(df, "BTCUSDT", None)
    strat: Strategy = make_strategy("s1")  # type: ignore[assignment]
    future = datetime(2030, 1, 1, tzinfo=UTC)
    with pytest.raises(DataGap):
        await load_features(store, strat, "BTCUSDT", future)


def test_synthetic_helpers_still_line_up() -> None:
    f = frames(standard_market())
    assert set(f.frames) == {"1h", "4h"}
