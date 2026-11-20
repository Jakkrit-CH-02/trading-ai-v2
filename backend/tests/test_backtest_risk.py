"""The backtester sizes and approves entries with the same Risk Engine as live."""

from decimal import Decimal

from app.backtest.engine import BacktestConfig, FeeModel, run_backtest
from app.backtest.registry import make_strategy, run_strategy
from app.core.models import Decision
from tests import synth
from tests.test_engine import FLAT, Stub, feats, sig

D = Decimal
FREE = FeeModel(taker=D(0), slippage=D(0))


def cfg(**kw: object) -> BacktestConfig:
    kw.setdefault("min_quote_volume_24h", 0.0)
    return BacktestConfig(**kw)  # type: ignore[arg-type]


def test_risk_engine_sizes_the_trade_within_half_a_percent_of_equity() -> None:
    f = feats([FLAT, FLAT, (100, 100.2, 94, 95), FLAT])
    r = run_backtest(Stub({0: sig(f, 0, stop=98, tp1=D(105))}), f, cfg(fees=FREE))
    [t] = r.trades
    assert t.exit_reason == "stop" and t.pnl_r < 0
    assert -D("0.005") * D(10_000) - D(1) <= t.pnl < 0  # about -0.5% of 10,000 at the stop


def test_trades_the_risk_engine_would_refuse_are_recorded_with_the_reason() -> None:
    f = feats([FLAT, FLAT, FLAT])
    r = run_backtest(Stub({0: sig(f, 0, stop=98)}), f, cfg())  # no target: R:R unverifiable
    assert r.trades == []
    assert r.signals[0].decision == Decision.REJECTED
    assert "NO_TARGET" in r.signals[0].reason and "risk engine" in r.signals[0].reason


def test_rr_target_lets_a_trailing_only_signal_pass_without_creating_an_exit() -> None:
    from dataclasses import replace

    f = feats([FLAT, FLAT, FLAT, FLAT])
    base = sig(f, 0, stop=98)  # entry 100, risk 2, no tp1
    with_ref = replace(base, rr_target=D(106))  # 3R reference: passes the R:R rule
    r = run_backtest(Stub({0: with_ref}), f, cfg())
    assert r.signals[0].decision == Decision.TAKEN
    [t] = r.trades
    assert t.exit_reason == "range_end"  # no tp1 exit was triggered by the reference target
    weak = replace(base, rr_target=D(101))  # R:R far below 1.5: still refused
    r2 = run_backtest(Stub({0: weak}), f, cfg())
    assert r2.trades == [] and "RR_TOO_LOW" in r2.signals[0].reason


def test_costs_make_a_1_5r_target_fail_the_after_cost_rr_rule() -> None:
    """SPEC 2.2 sets S1's TP1 at 1.5R; SPEC 3.5 demands R:R >= 1.5 after fees. Both cannot hold.

    This is executable documentation of that conflict: with realistic costs every such signal
    is rejected, with zero costs the same signal trades. Resolving it is a product decision."""
    rows = [FLAT, FLAT, FLAT]
    f = feats(rows)
    one_and_half_r = sig(f, 0, stop=98, tp1=D(103))  # entry 100, risk 2, target +3 = 1.5R
    free = run_backtest(Stub({0: one_and_half_r}), f, cfg(fees=FREE))
    costed = run_backtest(Stub({0: one_and_half_r}), f, cfg())
    assert free.signals[0].decision == Decision.TAKEN
    assert costed.signals[0].decision == Decision.REJECTED
    assert "RR_TOO_LOW" in costed.signals[0].reason


def test_s1_with_the_original_1_5r_target_is_rejected_but_2r_can_trade() -> None:
    fr = synth.frames(synth.standard_market())
    old = make_strategy("s1", {"tp1_r": 1.5})  # the SPEC 2.2 value: can never pass R:R after costs
    res_old = run_strategy(old, old.prepare(fr), cfg())
    rejected = [x for x in res_old.signals if x.decision == Decision.REJECTED]
    assert res_old.trades == [] and rejected
    assert all("RR_TOO_LOW" in x.reason for x in rejected)

    new = make_strategy("s1")  # default TP1 = 2R (decision 2026-11-20)
    res_new = run_strategy(new, new.prepare(fr), cfg())
    assert res_new.trades, "2R should satisfy R:R >= 1.5 after costs for normal stop distances"
    for x in res_new.signals:  # whatever is still refused is refused for a stated reason
        if x.decision == Decision.REJECTED:
            assert "risk engine" in x.reason or "cooldown" in x.reason or "liquidity" in x.reason


def test_circuit_breaker_state_is_shared_a_losing_streak_halves_later_sizes() -> None:
    gap = 30  # bars between trades: a new UTC day each time, so the daily-loss limit never trips
    rows: list[tuple[float, float, float, float]] = []
    starts: list[int] = []
    for _ in range(6):
        starts.append(len(rows))
        rows += [FLAT, (100, 100.2, 94, 95)] + [FLAT] * (gap - 2)  # entry, then stopped out
    f = feats(rows)
    stub = Stub({i: sig(f, i, stop=98, tp1=D(105)) for i in starts})
    r = run_backtest(stub, f, cfg(fees=FREE, cooldown_hours=0))
    qtys = [t.qty for t in r.trades]
    assert len(qtys) == 6 and all(t.pnl < 0 for t in r.trades)
    assert qtys[3] > qtys[0] * D("0.95")  # trades 1-4 are full size (equity barely moved)
    assert qtys[4] < qtys[0] * D("0.6")  # after 4 straight losses the engine halves risk


def test_drawdown_kill_switch_stops_all_further_entries() -> None:
    # a 12.5% account loss in one gap (25% exposure cap x 50% crash) trips the kill switch
    rows = [FLAT, FLAT, (50, 50.5, 49, 50)] + [FLAT] * 40
    f = feats(rows)
    stub = Stub({0: sig(f, 0, stop=99.0, tp1=D(160)), 30: sig(f, 30, stop=98, tp1=D(105))})
    r = run_backtest(stub, f, cfg(fees=FREE, risk_per_trade=D("0.01")))
    assert r.trades[0].pnl / D(10_000) < D("-0.12")
    later = r.signals[-1]
    assert later.decision == Decision.REJECTED and "KILL_SWITCH" in later.reason
    assert len(r.trades) == 1
