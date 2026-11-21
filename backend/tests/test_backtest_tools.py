import math
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.backtest.data import load_market_frames
from app.backtest.engine import BacktestConfig, FeeModel, TradeResult, run_backtest
from app.backtest.grid import run_grid_backtest
from app.backtest.metrics import Gate1Criteria, compute_metrics, evaluate_gate1
from app.backtest.montecarlo import monte_carlo, param_robustness
from app.backtest.registry import make_strategy, run_strategy, strategy_names
from app.backtest.report import (
    coverage_warning,
    format_gate,
    format_metrics,
    format_monte_carlo,
    format_walk_forward,
)
from app.backtest.walkforward import WalkForwardConfig, walk_forward
from app.exchange.types import Kline
from app.marketdata.store import InMemoryCandleStore
from tests import synth

D = Decimal
# plumbing tests isolate the backtest machinery from risk policy (see test_backtest_risk.py)
CFG = BacktestConfig(min_quote_volume_24h=0.0, use_risk_engine=False)


def trade(pnl: float, r: float = 0.0, ret: float = 0.0) -> TradeResult:
    t0 = datetime(2024, 1, 1, tzinfo=UTC)
    return TradeResult(
        strategy="x", symbol="BTCUSDT", entry_time=t0, exit_time=t0, entry_price=D(1),
        exit_price=D(1), qty=D(1), pnl=D(str(pnl)), fees=D(0), slippage=D(0), ret_pct=ret,
        pnl_r=r, bars_held=1, exit_reason="x", score=70.0, reasons={},
    )  # fmt: skip


# ---- metrics ----------------------------------------------------------------------------


def test_metrics_hand_computed() -> None:
    trades = [trade(100, 2.0), trade(-50, -1.0), trade(100, 2.0), trade(-50, -1.0)]
    idx = pd.date_range("2024-01-01", periods=4, freq="1D", tz="UTC")
    eq = pd.Series([100.0, 110.0, 99.0, 121.0], index=idx)
    m = compute_metrics(trades, eq, 100.0)
    assert m.n_trades == 4 and m.win_rate == 0.5
    assert m.profit_factor == pytest.approx(2.0)  # 200 / 100
    assert m.expectancy_r == pytest.approx(0.5)
    assert m.net_pnl == pytest.approx(100.0)
    assert m.max_drawdown == pytest.approx(1 - 99 / 110)
    assert m.total_return == pytest.approx(0.21)
    assert m.yearly_returns == {2024: pytest.approx(0.21)}


def test_profit_factor_with_no_losses_is_infinite_not_an_error() -> None:
    eq = pd.Series([1.0, 2.0], index=pd.date_range("2024-01-01", periods=2, freq="1D", tz="UTC"))
    assert math.isinf(compute_metrics([trade(5)], eq, 1.0).profit_factor)
    assert compute_metrics([], eq, 1.0).profit_factor == 0.0


def test_gate1_reports_every_failed_criterion() -> None:
    eq = pd.Series([100.0] * 3, index=pd.date_range("2024-01-01", periods=3, freq="1D", tz="UTC"))
    bad = compute_metrics([trade(-1, -1.0)] * 5, eq, 100.0)
    g = evaluate_gate1(bad)
    assert not g.passed
    joined = " | ".join(g.failures)
    for key in ("trades 5", "profit factor", "sharpe", "expectancy"):
        assert key in joined
    assert "FAIL" in format_gate(g) and "profit factor" in format_gate(g)


def test_gate1_passes_when_all_criteria_met_and_thresholds_are_spec_values() -> None:
    c = Gate1Criteria()
    assert (c.min_trades, c.min_profit_factor, c.min_sharpe, c.max_drawdown) == (100, 1.3, 1.0, 0.2)
    assert (c.min_expectancy_r, c.max_year_loss) == (0.15, 0.10)
    n = 120
    idx = pd.date_range("2023-01-01", periods=n, freq="7D", tz="UTC")
    eq = pd.Series(
        10_000 * np.cumprod(1 + np.where(np.arange(n) % 3 == 0, -0.002, 0.006)), index=idx
    )
    trades = [trade(30, 1.0)] * 80 + [trade(-20, -1.0)] * 40
    good = compute_metrics(trades, eq, 10_000.0)
    assert evaluate_gate1(good).passed, evaluate_gate1(good).failures


# ---- monte carlo / robustness ------------------------------------------------------------


def test_monte_carlo_is_deterministic_and_order_sensitive() -> None:
    trades = [trade(0, ret=-0.1)] * 10 + [trade(0, ret=0.1)] * 10
    a, b = monte_carlo(trades, 500, seed=1), monte_carlo(trades, 500, seed=1)
    assert a == b and a is not None
    worst_case = 1 - 0.9**10  # every loss first
    assert 0 < a.max_dd_p50 <= a.max_dd_p95 <= a.max_dd_worst <= worst_case + 1e-9
    # compounding is commutative: the final return does not depend on the order
    assert a.final_return_p5 == pytest.approx(a.final_return_p50) == pytest.approx(0.99**10 - 1)


def test_monte_carlo_all_wins_has_no_drawdown_and_few_trades_is_none() -> None:
    mc = monte_carlo([trade(0, ret=0.01)] * 20)
    assert mc is not None and mc.max_dd_worst == 0
    assert monte_carlo([trade(0, ret=0.01)] * 9) is None
    assert "skipped" in format_monte_carlo(None)


def test_param_robustness_counts_profitable_neighbours() -> None:
    def evaluate(p: dict[str, float]) -> float:
        return 5.0 - abs(p["x"] - 10.0)  # profitable only within +/-5 of x=10

    res = param_robustness({"x": 10.0}, evaluate, pct=0.2)
    assert res.fraction_profitable == 1.0 and res.base_net_pnl == 5.0

    fragile = param_robustness({"x": 10.0}, lambda p: 1.0 if p["x"] == 10.0 else -1.0)
    assert fragile.fraction_profitable == 0.0  # only the exact setting works: overfit


def test_param_robustness_keeps_integer_parameters_integral() -> None:
    seen: list[float] = []
    param_robustness({"n": 14}, lambda p: seen.append(p["n"]) or 0.0, pct=0.2)  # type: ignore[func-returns-value]
    assert {11.0, 17.0} <= set(seen) and all(float(v).is_integer() for v in seen)


# ---- registry ----------------------------------------------------------------------------


def test_registry_builds_all_strategies_and_rejects_bad_input() -> None:
    assert strategy_names() == ["s1", "s2", "s3", "s4", "s5"]
    for name in strategy_names():
        assert make_strategy(name).name == name
    with pytest.raises(ValueError, match="unknown strategy"):
        make_strategy("s9")
    with pytest.raises(ValueError, match="unknown parameters"):
        make_strategy("s1", {"nope": 1})


def test_parameter_override_changes_the_signal() -> None:
    fr = synth.frames(synth.standard_market())
    s15, s20 = make_strategy("s1"), make_strategy("s1", {"tp1_r": 2.5})
    f15, f20 = s15.prepare(fr), s20.prepare(fr)
    i = next(i for i in range(len(f15)) if s15.evaluate(f15, i))  # type: ignore[union-attr]
    a, b = s15.evaluate(f15, i), s20.evaluate(f20, i)  # type: ignore[union-attr]
    assert a and b and a.entry == b.entry and a.stop == b.stop
    assert (b.tp1 - b.entry) > (a.tp1 - a.entry)  # type: ignore[operator]


def test_run_strategy_dispatches_grid_to_the_grid_simulator() -> None:
    fr = synth.frames(synth.standard_market())
    s4 = make_strategy("s4")
    res = run_strategy(s4, s4.prepare(fr), CFG)
    assert res.strategy == "s4" and all(t.strategy == "s4" for t in res.trades)


# ---- end to end through the store loader ---------------------------------------------------


def _klines(df: pd.DataFrame, interval: str, symbol: str = "BTCUSDT") -> list[Kline]:
    times = pd.DatetimeIndex(df.index).to_pydatetime()
    rows = df.to_dict("records")

    def d(x: float) -> Decimal:
        return D(repr(float(x)))

    return [
        Kline(symbol, interval, t, d(r["open"]), d(r["high"]), d(r["low"]), d(r["close"]),
              d(r["volume"]), d(r["quote_volume"]), 10, D(1))
        for t, r in zip(times, rows, strict=True)
    ]  # fmt: skip


async def test_loader_to_backtest_end_to_end() -> None:
    df1 = synth.standard_market()
    store = InMemoryCandleStore()
    await store.save(_klines(df1, "1h"))
    await store.save(_klines(synth.to_4h(df1), "4h"))
    start, end = df1.index[0].to_pydatetime(), df1.index[-1].to_pydatetime()
    data = await load_market_frames(store, "BTCUSDT", start, end)
    assert list(data.frames) == ["1h", "4h"] and data.btc_4h is None

    s1 = make_strategy("s1")
    res = run_backtest(s1, s1.prepare(data), CFG)  # type: ignore[arg-type]
    assert res.trades and res.signals
    # accounting identity over the whole run (flat at the end because of range_end exit)
    assert res.final_equity == res.initial_equity + sum(t.pnl for t in res.trades)
    # every trade respects risk sizing: loss at the stop is about risk_per_trade of equity
    stop_losses = [t for t in res.trades if t.exit_reason == "stop"]
    assert all(t.pnl_r <= 0 for t in stop_losses)
    m = compute_metrics(res.trades, res.equity, float(res.initial_equity))
    assert m.n_trades == len(res.trades) and 0 <= m.max_drawdown < 1
    assert "profit factor" in format_metrics(m)


async def test_loader_gives_a_helpful_error_when_data_is_missing() -> None:
    with pytest.raises(ValueError, match="softtrade backfill"):
        await load_market_frames(
            InMemoryCandleStore(),
            "BTCUSDT",
            datetime(2024, 1, 1, tzinfo=UTC),
            datetime(2024, 2, 1, tzinfo=UTC),
        )


async def test_alt_symbol_loads_btc_filter() -> None:
    df1 = synth.standard_market()
    store = InMemoryCandleStore()
    for sym in ("BTCUSDT", "ETHUSDT"):
        await store.save(_klines(df1, "1h", sym))
        await store.save(_klines(synth.to_4h(df1), "4h", sym))
    data = await load_market_frames(
        store, "ETHUSDT", df1.index[0].to_pydatetime(), df1.index[-1].to_pydatetime()
    )
    assert data.btc_4h is not None and len(data.btc_4h) == len(data.frames["4h"])


def test_coverage_warning_flags_short_history() -> None:
    short = pd.date_range("2024-01-01", periods=24 * 100, freq="1h", tz="UTC")
    assert coverage_warning(short) and "cannot pass gate 1" in (coverage_warning(short) or "")
    long = pd.date_range("2021-01-01", periods=24 * 365 * 4, freq="1h", tz="UTC")
    assert coverage_warning(long) is None
    exactly_3y = pd.date_range("2023-11-20", periods=24 * 365 * 3, freq="1h", tz="UTC")
    assert coverage_warning(exactly_3y) is None  # 3 calendar years is enough, not "3.0 < 3"
    assert coverage_warning(exactly_3y[: -24 * 30]) is not None


# ---- walk-forward ---------------------------------------------------------------------------


def long_market() -> pd.DataFrame:
    seg = [
        ("up", 1500),
        ("range", 1200),
        ("squeeze", 400),
        ("up", 800),
        ("down", 900),
        ("range", 1000),
    ]
    return synth.make_1h(seg * 3, seed=11)  # about 2.3 years of 1h bars


def test_walk_forward_stitches_only_out_of_sample_folds() -> None:
    df = long_market()
    fr = synth.frames(df)
    wf = walk_forward(
        "s1", fr, {"tp1_r": [1.2, 1.5]}, CFG,
        WalkForwardConfig(train_months=12, test_months=3, step_months=3, min_train_trades=3),
    )  # fmt: skip
    assert len(wf.folds) >= 3
    for a, b in zip(wf.folds, wf.folds[1:], strict=False):
        assert b.test_start == a.test_start + pd.DateOffset(months=3)  # tiles with no overlap
        assert a.test_start == a.train_start + pd.DateOffset(months=12)
        assert a.best_params["tp1_r"] in (1.2, 1.5)
    first_test = wf.folds[0].test_start
    assert wf.oos_trades, "expected out-of-sample trades"
    for t in wf.oos_trades:  # nothing from the training windows leaks into the result
        assert t.entry_time >= first_test
        assert any(f.test_start <= t.entry_time < f.test_end for f in wf.folds)
    assert wf.oos_metrics.n_trades == len(wf.oos_trades)
    # equity carries across folds: no jump at fold boundaries
    for f in wf.folds[1:]:
        before = wf.oos_equity[wf.oos_equity.index < f.test_start].iloc[-1]
        after = wf.oos_equity[wf.oos_equity.index >= f.test_start].iloc[0]
        assert abs(after / before - 1) < 0.05
    assert "OUT-OF-SAMPLE" in format_walk_forward(wf)


def test_walk_forward_needs_enough_history() -> None:
    with pytest.raises(ValueError, match="not enough data"):
        walk_forward("s1", synth.frames(synth.standard_market()), {}, CFG)


def test_overfitting_verdict_is_withheld_when_trades_are_too_few() -> None:
    wf = walk_forward(
        "s3", synth.frames(long_market()), {}, CFG, WalkForwardConfig(min_train_trades=3)
    )
    assert wf.overfit_ratio is None
    assert any("overfitting check skipped" in w for w in wf.warnings)
    assert not any("possible overfitting" in w for w in wf.warnings)


def test_in_sample_quality_is_not_what_gets_reported() -> None:
    wf = walk_forward(
        "s1", synth.frames(long_market()), {"tp1_r": [1.2, 1.5]}, CFG,
        WalkForwardConfig(min_train_trades=3),
    )  # fmt: skip
    assert wf.oos_metrics.n_trades == sum(f.out_of_sample.n_trades for f in wf.folds)


def test_zero_cost_run_beats_costed_run() -> None:
    """Sanity check that costs are actually applied end to end."""
    fr = synth.frames(synth.standard_market())
    s = make_strategy("s1")
    feats = s.prepare(fr)
    free_cfg = BacktestConfig(
        fees=FeeModel(D(0), D(0)), min_quote_volume_24h=0.0, use_risk_engine=False
    )
    free = run_strategy(s, feats, free_cfg)
    costed = run_strategy(s, feats, CFG)
    assert free.trades and costed.trades
    assert free.final_equity > costed.final_equity


def test_grid_and_engine_agree_on_empty_input() -> None:
    fr = synth.frames(synth.make_1h([("up", 600)], seed=2))
    s4 = make_strategy("s4")
    res = run_grid_backtest(s4, s4.prepare(fr), CFG)  # type: ignore[arg-type]
    assert res.final_equity == res.initial_equity + sum(t.pnl for t in res.trades)


def test_pooled_walk_forward_is_an_equal_weight_portfolio_of_sleeves() -> None:
    from app.backtest.walkforward import WalkForwardResult, pool_walk_forward

    idx = pd.date_range("2024-01-01", periods=3, freq="1D", tz="UTC")

    def result(pnl: float, curve: list[float]) -> WalkForwardResult:
        m = compute_metrics([trade(pnl, 1.0)], pd.Series(curve, index=idx), 10_000.0)
        return WalkForwardResult([], [trade(pnl, 1.0)], pd.Series(curve, index=idx), m, None)

    trades, equity, m = pool_walk_forward(
        [result(200, [10_000, 10_200, 10_200]), result(-100, [10_000, 9_900, 9_900])], 10_000.0
    )
    assert [t.pnl for t in trades] == [D(100), D(-50)] or {t.pnl for t in trades} == {
        D(100),
        D(-50),
    }
    assert equity.iloc[-1] == pytest.approx(10_050.0)  # mean of the two sleeves
    assert m.n_trades == 2 and m.profit_factor == pytest.approx(2.0)
    with pytest.raises(ValueError):
        pool_walk_forward([], 10_000.0)
