"""Backtest engine accounting and timing rules, on hand-built bars with a stub strategy."""

from datetime import timedelta
from decimal import Decimal

import pandas as pd
import pytest

from app.backtest.engine import BacktestConfig, FeeModel, run_backtest
from app.core.models import Decision, Side
from app.strategies.features import Features, dec
from app.strategies.types import Signal, TrailSpec
from tests.helpers import T0

D = Decimal
FREE = FeeModel(taker=D(0), slippage=D(0))


def feats(rows: list[tuple[float, float, float, float]], qv: float = 1e12) -> Features:
    idx = pd.DatetimeIndex([T0 + timedelta(hours=i) for i in range(len(rows))])
    df = pd.DataFrame(rows, columns=["open", "high", "low", "close"], index=idx)
    df["volume"] = 100.0
    df["qv24h"] = qv
    return Features.from_frame("BTCUSDT", "1h", df)


def sig(f: Features, i: int, stop: float, s_tech: float = 100.0, **kw: object) -> Signal:
    return Signal(
        strategy="stub",
        symbol="BTCUSDT",
        side=Side.BUY,
        bar_time=f.time(i),
        entry=dec(f["close"][i]),
        stop=dec(stop),
        s_tech=s_tech,
        **kw,  # type: ignore[arg-type]
    )


class Stub:
    name = "stub"
    exec_interval = "1h"

    def __init__(self, signals: dict[int, Signal]) -> None:
        self.signals = signals

    def prepare(self, data: object) -> Features:
        raise NotImplementedError

    def evaluate(self, f: Features, i: int) -> Signal | None:
        return self.signals.get(i)


def cfg(**kw: object) -> BacktestConfig:
    kw.setdefault("fees", FREE)
    kw.setdefault("min_quote_volume_24h", 0.0)
    kw.setdefault("use_risk_engine", False)  # these tests isolate timing/accounting rules
    return BacktestConfig(**kw)  # type: ignore[arg-type]


FLAT = (100.0, 100.5, 99.5, 100.0)


def test_entry_fills_at_next_open_not_signal_close() -> None:
    f = feats([FLAT, (101, 102, 100.5, 101.5), (101.5, 102, 101, 101.5)])
    r = run_backtest(Stub({0: sig(f, 0, stop=95)}), f, cfg())
    t = r.trades[0]
    assert t.entry_price == D(101) and t.exit_reason == "range_end"


def test_stop_and_target_in_same_bar_stop_wins() -> None:
    f = feats([FLAT, (100, 110, 94, 105), FLAT])
    r = run_backtest(Stub({0: sig(f, 0, stop=95, tp1=D("107.5"))}), f, cfg())
    t = r.trades[0]
    assert t.exit_reason == "stop"
    assert t.exit_price == D(95)
    assert t.pnl_r == pytest.approx(-1.0)
    assert t.pnl == D(-50)  # 10000 * 0.5% risk


def test_gap_through_stop_exits_at_the_open_not_the_stop() -> None:
    f = feats([FLAT, (100, 100.2, 99.8, 100), (90, 91, 89, 90)])
    r = run_backtest(Stub({0: sig(f, 0, stop=95)}), f, cfg())
    assert r.trades[0].exit_price == D(90) and r.trades[0].pnl_r < -1.0


def test_tp1_takes_half_and_moves_stop_to_breakeven() -> None:
    f = feats([FLAT, (100, 108, 101, 107), (107, 107, 99.5, 100), FLAT])
    r = run_backtest(Stub({0: sig(f, 0, stop=95, tp1=D("107.5"))}), f, cfg())
    t = r.trades[0]
    assert t.exit_reason == "breakeven"
    assert t.pnl == D("37.5")  # 5 units at +7.5, other 5 out at entry (100)


def test_tp1_bar_that_also_falls_back_to_breakeven_exits_immediately() -> None:
    f = feats([FLAT, (100, 108, 99, 107), FLAT])
    r = run_backtest(Stub({0: sig(f, 0, stop=95, tp1=D("107.5"))}), f, cfg())
    assert r.trades[0].exit_reason == "breakeven" and r.trades[0].bars_held == 1


def test_full_target_closes_the_position() -> None:
    f = feats([FLAT, (100, 104, 99.5, 103), FLAT])
    s = sig(f, 0, stop=95, tp1=D(102), tp1_close_fraction=D(1))
    t = run_backtest(Stub({0: s}), f, cfg()).trades[0]
    assert t.exit_reason == "tp1" and t.pnl == D(20)


def test_entry_gapping_below_stop_is_rejected_not_traded() -> None:
    f = feats([FLAT, (90, 91, 89, 90), FLAT])
    r = run_backtest(Stub({0: sig(f, 0, stop=95)}), f, cfg())
    assert r.trades == []
    assert r.signals[0].decision == Decision.REJECTED


def test_time_stop_exits_at_close_after_n_bars() -> None:
    f = feats([FLAT, *[(100, 100.4, 99.6, 100.2)] * 6])
    r = run_backtest(Stub({0: sig(f, 0, stop=90, time_stop_bars=3)}), f, cfg())
    t = r.trades[0]
    assert t.exit_reason == "time_stop" and t.bars_held == 3


def test_false_breakout_exits_when_price_closes_back_below_level() -> None:
    f = feats([FLAT, (100.5, 101, 99, 99.5), FLAT, FLAT])
    r = run_backtest(Stub({0: sig(f, 0, stop=90, false_breakout=(D(100), 3))}), f, cfg())
    assert r.trades[0].exit_reason == "false_breakout"


def test_trailing_stop_ratchets_up_and_never_down() -> None:
    rows = [FLAT, (100, 101, 99.5, 100.5)]
    price = 100.5
    for _ in range(30):  # steady climb, ATR stays small
        rows.append((price, price + 1, price - 0.3, price + 0.8))
        price += 0.8
    rows.append((price, price, price - 8, price - 7))  # sharp drop hits the trail
    f = feats(rows)
    s = sig(f, 0, stop=90, trail=TrailSpec(mult=2.0, period=5, after_tp1=False))
    t = run_backtest(Stub({0: s}), f, cfg()).trades[0]
    assert t.exit_reason == "trail" and t.pnl > 0 and t.exit_price > t.entry_price


def test_cooldown_blocks_reentry_after_a_stop_loss() -> None:
    rows = [FLAT, (100, 100.2, 94, 95)] + [FLAT] * 8
    f = feats(rows)
    stub = Stub({0: sig(f, 0, stop=96), 3: sig(f, 3, stop=96), 6: sig(f, 6, stop=96)})
    r = run_backtest(stub, f, cfg())
    decisions = [(s.signal.bar_time, s.decision, s.reason) for s in r.signals]
    assert decisions[1][1] == Decision.REJECTED and "cooldown" in decisions[1][2]  # bar 3
    assert decisions[2][1] == Decision.TAKEN  # bar 6, cooldown (4 bars after bar 1) is over


def test_low_score_signal_is_recorded_but_not_traded() -> None:
    f = feats([FLAT, FLAT, FLAT])
    r = run_backtest(Stub({0: sig(f, 0, stop=95, s_tech=60.0)}), f, cfg())
    assert r.trades == [] and r.signals[0].decision == Decision.SKIPPED


def test_half_score_trades_half_size() -> None:
    f = feats([FLAT, FLAT, FLAT])
    full = run_backtest(Stub({0: sig(f, 0, stop=95, s_tech=100)}), f, cfg()).trades[0]
    half = run_backtest(Stub({0: sig(f, 0, stop=95, s_tech=80)}), f, cfg()).trades[0]
    assert half.qty == full.qty / 2  # score 63.5 -> 0.5x


def test_liquidity_filter_rejects_illiquid_symbol() -> None:
    f = feats([FLAT, FLAT, FLAT], qv=1e6)
    r = run_backtest(Stub({0: sig(f, 0, stop=95)}), f, cfg(min_quote_volume_24h=50e6))
    assert r.trades == [] and r.signals[0].reason == "liquidity filter"


def test_exposure_cap_limits_position_size() -> None:
    f = feats([FLAT, FLAT, FLAT])
    t = run_backtest(Stub({0: sig(f, 0, stop=99.9)}), f, cfg()).trades[0]  # tiny stop
    assert t.qty * t.entry_price <= D(10_000) * D("0.25")


def test_costs_are_charged_and_ledger_balances() -> None:
    f = feats([FLAT, (100, 100.5, 94, 95), FLAT])
    c = BacktestConfig(min_quote_volume_24h=0.0, use_risk_engine=False)  # 0.1% fee, 0.05% slip
    r = run_backtest(Stub({0: sig(f, 0, stop=95)}), f, c)
    t = r.trades[0]
    assert t.entry_price == D(100) * (1 + D("0.0005"))
    assert t.exit_price == D(95) * (1 - D("0.0005"))
    assert t.pnl == t.qty * (t.exit_price - t.entry_price) - t.fees
    assert t.fees == t.qty * t.entry_price * D("0.001") + t.qty * t.exit_price * D("0.001")
    assert r.final_equity == r.initial_equity + sum(x.pnl for x in r.trades)
    assert t.pnl_r < -1.0  # costs make the loss bigger than 1R


def test_equity_curve_is_marked_to_market_each_bar() -> None:
    f = feats([FLAT, (100, 103, 100, 102), (102, 106, 101, 105), (105, 105, 104, 104)])
    r = run_backtest(Stub({0: sig(f, 0, stop=90)}), f, cfg())
    assert len(r.equity) == 4
    assert r.equity.iloc[0] == 10_000
    assert r.equity.iloc[2] > r.equity.iloc[1]  # open profit shows up before the exit


def test_range_slicing_and_equity_carry() -> None:
    f = feats([FLAT, FLAT, (100, 105, 99, 104), FLAT, FLAT])
    s = Stub({1: sig(f, 1, stop=95, tp1=D(103), tp1_close_fraction=D(1))})
    r = run_backtest(s, f, cfg(), start=1, end=5, initial_equity=D(20_000))
    assert r.initial_equity == D(20_000) and r.final_equity > D(20_000)
    assert len(r.equity) == 4
