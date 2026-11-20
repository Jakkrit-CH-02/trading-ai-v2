from collections.abc import Sequence
from datetime import timedelta
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, FeeModel
from app.backtest.grid import run_grid_backtest
from app.backtest.montecarlo import monte_carlo
from app.strategies.features import Features, dec
from app.strategies.params import S4Params
from app.strategies.s4_grid import S4Grid
from tests import synth
from tests.helpers import T0

D = Decimal
FREE = FeeModel(taker=D(0), slippage=D(0))


def grid_feats(
    rows: Sequence[tuple[float, float, float, float]],
    regimes: list[str] | None = None,
    support: float = 90.0,
    resistance: float = 110.0,
    atr: float = 2.0,
) -> Features:
    idx = pd.DatetimeIndex([T0 + timedelta(hours=i) for i in range(len(rows))])
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 100.0
    df["qv24h"] = 1e12
    df["atr"] = atr
    df["support"] = support
    df["resistance"] = resistance
    df["regime4"] = regimes or ["RANGE"] * len(rows)
    df["btc_regime"] = "RANGE"
    df["adx4"] = 15.0
    return Features.from_frame("BTCUSDT", "1h", df)


def cfg(**kw: object) -> BacktestConfig:
    return BacktestConfig(fees=FREE, min_quote_volume_24h=0.0, **kw)  # type: ignore[arg-type]


LEVELS = np.linspace(90, 110, 20)  # what plan_grid builds for support 90 / resistance 110


# ---- planning ---------------------------------------------------------------------------


def test_plan_uses_most_levels_the_fees_allow() -> None:
    f = grid_feats([(100, 101, 99, 100)])
    plan = S4Grid().plan_grid(f, 0, round_trip_fee=0.002)
    assert plan is not None and len(plan.levels) == 20
    spacing = float(plan.levels[1] - plan.levels[0])
    assert spacing >= 3 * 0.002 * 100  # SPEC: spacing >= 3x round-trip fee
    assert plan.lower == D(90) and plan.upper == D(110) and plan.stop == D(88)  # lower - 1 ATR


def test_plan_reduces_levels_when_range_is_narrow_and_refuses_when_too_tight() -> None:
    narrow = grid_feats([(100, 101, 99, 100)], support=96.0, resistance=104.0)
    plan = S4Grid().plan_grid(narrow, 0, round_trip_fee=0.002)
    assert plan is not None and 10 <= len(plan.levels) < 20
    tight = grid_feats([(100, 101, 99, 100)], support=99.5, resistance=100.5)
    assert S4Grid().plan_grid(tight, 0, round_trip_fee=0.002) is None


def test_plan_requires_range_regime_and_price_inside_the_range() -> None:
    trending = grid_feats([(100, 101, 99, 100)], regimes=["TREND_UP"])
    assert S4Grid().plan_grid(trending, 0, 0.002) is None
    broke_out = grid_feats([(111, 113, 110, 112)])
    assert S4Grid().plan_grid(broke_out, 0, 0.002) is None


def test_s4_features_have_no_lookahead() -> None:
    df = synth.standard_market()
    s = S4Grid()
    full = s.prepare(synth.frames(df))
    for cut in range(1801, 6800, 331):
        part = s.prepare(synth.truncate(df, cut))
        n = len(part)
        for col, arr in part.cols.items():
            want = full.cols[col][:n]
            if arr.dtype == object:
                assert arr.tolist() == want.tolist(), col
            else:
                np.testing.assert_allclose(arr, want, rtol=1e-9, atol=1e-9, equal_nan=True)


# ---- simulation -------------------------------------------------------------------------


def test_buy_on_dip_then_sell_one_level_up() -> None:
    rows = [
        (100, 100.5, 99.5, 100),  # plan is made at this close
        (100, 100.2, 97.9, 98.5),  # dips through levels 98.42 and 99.47 -> two buys
        (98.5, 100.6, 99.0, 100.0),  # rallies: both lots sell one level up
        (100, 100.2, 99.8, 100),
    ]
    f = grid_feats(rows)
    r = run_grid_backtest(S4Grid(), f, cfg())
    tps = [t for t in r.trades if t.exit_reason == "grid_tp"]
    assert len(tps) == 2
    for t in tps:
        k = int(np.argmin(np.abs(LEVELS - float(t.entry_price))))
        assert t.entry_price == dec(LEVELS[k])
        target = dec(LEVELS[k + 1])
        assert t.exit_price == target and t.pnl == t.qty * (target - t.entry_price)
        assert t.pnl > 0 and t.bars_held >= 2  # never completes inside its own buy bar


def test_buy_and_its_own_sell_cannot_happen_in_one_bar() -> None:
    rows = [(100, 100.5, 99.5, 100), (100, 103, 97, 100), (100, 100.2, 99.8, 100)]
    r = run_grid_backtest(S4Grid(), grid_feats(rows), cfg())
    assert not any(t.exit_reason == "grid_tp" and t.bars_held < 2 for t in r.trades)


def test_closing_below_the_stop_liquidates_everything() -> None:
    rows = [
        (100, 100.5, 99.5, 100),
        (100, 100.2, 97.9, 98.5),  # buys
        (98.5, 98.6, 86, 87.0),  # closes below stop (88): everything is sold at the close
        (87, 88, 86, 87),
    ]
    r = run_grid_backtest(S4Grid(), grid_feats(rows), BacktestConfig(min_quote_volume_24h=0.0))
    stops = [t for t in r.trades if t.exit_reason == "grid_stop"]
    assert stops and all(t.pnl < 0 for t in stops)
    # a market exit pays slippage on top of fees
    assert all(t.exit_price == D("87") * (1 - D("0.0005")) for t in stops)


def test_regime_change_closes_the_grid() -> None:
    rows = [
        (100, 100.5, 99.5, 100),
        (100, 100.2, 97.9, 98.5),
        (98.5, 99.6, 98.4, 99.5),
        (99.5, 100, 99, 99.8),
    ]
    f = grid_feats(rows, regimes=["RANGE", "RANGE", "TREND_UP", "TREND_UP"])
    r = run_grid_backtest(S4Grid(), f, cfg())
    assert any(t.exit_reason == "regime_change" for t in r.trades)


def test_ledger_balances_and_exposure_is_bounded() -> None:
    rng = np.random.default_rng(5)
    price, rows = 100.0, []
    for _ in range(400):  # random walk inside a range
        o = price
        price = float(np.clip(price + rng.normal(0, 0.8), 92, 108))
        rows.append((o, max(o, price) + 0.3, min(o, price) - 0.3, price))
    f = grid_feats(rows)
    r = run_grid_backtest(S4Grid(), f, BacktestConfig(min_quote_volume_24h=0.0))
    assert r.trades, "expected the walk to complete some grid cycles"
    assert r.final_equity == r.initial_equity + sum(t.pnl for t in r.trades)  # flat at the end
    allocation = D(repr(S4Params().allocation)) * r.initial_equity
    assert max(t.qty * t.entry_price for t in r.trades) <= allocation
    assert (r.equity > 0).all()
    # returns are on equity, so each lot is a small fraction and Monte Carlo stays sane
    assert max(abs(t.ret_pct) for t in r.trades) < 0.02
    mc = monte_carlo(r.trades, 200, seed=1)
    assert mc is not None and mc.max_dd_p95 < 0.5


def test_nothing_happens_outside_range_regime() -> None:
    f = grid_feats([(100, 101, 99, 100)] * 30, regimes=["TREND_UP"] * 30)
    r = run_grid_backtest(S4Grid(), f, cfg())
    assert r.trades == [] and r.final_equity == r.initial_equity


@pytest.mark.parametrize("bad", [0.0])
def test_zero_fee_spacing_still_respects_min_levels(bad: float) -> None:
    f = grid_feats([(100, 101, 99, 100)])
    plan = S4Grid().plan_grid(f, 0, round_trip_fee=bad)
    assert plan is not None and len(plan.levels) == 20
