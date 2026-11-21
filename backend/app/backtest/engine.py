"""Event-driven, bar-by-bar backtester (SPEC 11.1) for single-position strategies (S1-S3).

Timing rules that keep results honest:
- A signal is computed at the *close* of bar ``i`` from features ``<= i`` only.
- The entry fills at the *open* of bar ``i+1`` (taker + slippage). If that open is already
  at/below the stop, the trade is skipped.
- Stops and targets are managed intrabar with the worst case first: if a bar's low reaches
  the stop it exits at the stop (or the open on a gap) even if its high also reached the
  target.
- Trailing stops and close-based exits use bar-close data and take effect from the next bar.
- Fees (taker on every fill) and slippage (per side) are always charged. Money is Decimal.

Position sizing here is a *simplified placeholder* of SPEC 3.1 (risk %, score factor,
per-symbol exposure cap). The real Risk Engine arrives in Phase 3 and replaces it.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any

import numpy as np
import pandas as pd

from app.backtest.riskgate import RiskGate
from app.core.models import Decision
from app.exchange.types import INTERVAL_MS
from app.marketdata import indicators as ind
from app.strategies.base import Strategy
from app.strategies.decision import decide_at_close
from app.strategies.features import Features, dec
from app.strategies.scoring import ScoreResult, ScoreWeights
from app.strategies.types import Signal

QTY_STEP = Decimal("0.00000001")
ZERO_QTY = Decimal(0)


@dataclass(frozen=True, slots=True)
class FeeModel:
    """Conservative defaults (SPEC 11.1): taker on every order, 0.05% slippage per side.
    Check the current Binance fee tier before trusting results."""

    taker: Decimal = Decimal("0.001")
    slippage: Decimal = Decimal("0.0005")


@dataclass(frozen=True, slots=True)
class BacktestConfig:
    initial_equity: Decimal = Decimal(10_000)
    risk_per_trade: Decimal = Decimal("0.005")
    max_symbol_exposure: Decimal = Decimal("0.25")
    min_notional: Decimal = Decimal(10)
    cooldown_hours: int = 4
    min_quote_volume_24h: float = 50_000_000.0  # SPEC 2.4 liquidity filter; 0 disables
    # Size and approve entries with the real Risk Engine (same code as live). False keeps the
    # old placeholder sizing; only meant for isolated timing/accounting tests.
    use_risk_engine: bool = True
    fees: FeeModel = field(default_factory=FeeModel)
    weights: ScoreWeights = field(default_factory=ScoreWeights)


@dataclass(slots=True)
class TradeResult:
    strategy: str
    symbol: str
    entry_time: datetime
    exit_time: datetime
    entry_price: Decimal
    exit_price: Decimal  # average over all exit legs
    qty: Decimal
    pnl: Decimal  # USDT, after fees and slippage
    fees: Decimal
    slippage: Decimal  # estimated slippage cost, USDT (already inside pnl)
    ret_pct: float  # pnl / equity before the trade
    pnl_r: float  # pnl / initial price risk
    bars_held: int
    exit_reason: str
    score: float
    reasons: dict[str, Any]


@dataclass(slots=True)
class SignalRecord:
    """Every signal is kept, including skipped/rejected ones (SPEC 1.5, table `signals`)."""

    signal: Signal
    score: ScoreResult
    decision: Decision
    reason: str = ""


@dataclass(slots=True)
class BacktestResult:
    strategy: str
    symbol: str
    trades: list[TradeResult]
    signals: list[SignalRecord]
    equity: pd.Series  # float, indexed by bar open time, marked to market each bar
    initial_equity: Decimal
    final_equity: Decimal
    config: BacktestConfig


@dataclass(slots=True)
class _Pos:
    signal: Signal
    score: ScoreResult
    idx_open: int
    entry_time: datetime
    entry: Decimal
    qty0: Decimal
    qty: Decimal
    stop: Decimal
    stop0: Decimal
    tp1_done: bool
    highest: Decimal
    cash_before: Decimal
    stop_kind: str = "stop"
    fees: Decimal = Decimal(0)
    slip_cost: Decimal = Decimal(0)
    exit_value: Decimal = Decimal(0)
    exit_qty: Decimal = Decimal(0)


def _atr_array(f: Features, period: int, cache: dict[int, np.ndarray[Any, Any]]) -> Any:
    if period not in cache:
        s = ind.atr(
            pd.Series(f["high"]), pd.Series(f["low"]), pd.Series(f["close"]), period
        ).to_numpy()
        cache[period] = s
    return cache[period]


def run_backtest(
    strategy: Strategy,
    feats: Features,
    cfg: BacktestConfig | None = None,
    start: int = 0,
    end: int | None = None,
    initial_equity: Decimal | None = None,
) -> BacktestResult:
    cfg = cfg or BacktestConfig()
    fee, slip = cfg.fees.taker, cfg.fees.slippage
    n = len(feats) if end is None else min(end, len(feats))
    cash = initial_equity if initial_equity is not None else cfg.initial_equity
    start_cash = cash
    bar_ms = INTERVAL_MS[feats.interval]
    cooldown_bars = math.ceil(cfg.cooldown_hours * 3_600_000 / bar_ms)

    gate = (
        RiskGate(cfg.risk_per_trade, fee, slip, cfg.max_symbol_exposure, cfg.min_notional, cash)
        if cfg.use_risk_engine
        else None
    )
    pos: _Pos | None = None
    pending: tuple[Signal, ScoreResult, SignalRecord] | None = None
    cooldown_until = -1
    trades: list[TradeResult] = []
    records: list[SignalRecord] = []
    equity_pts: list[tuple[pd.Timestamp, float]] = []
    atr_cache: dict[int, np.ndarray[Any, Any]] = {}

    def sell(p: _Pos, qty_leg: Decimal, raw_price: Decimal) -> Decimal:
        nonlocal cash
        px = raw_price * (1 - slip)
        gross = qty_leg * px
        fee_leg = gross * fee
        cash += gross - fee_leg
        p.qty -= qty_leg
        p.fees += fee_leg
        p.exit_value += gross
        p.exit_qty += qty_leg
        p.slip_cost += qty_leg * raw_price * slip
        return px

    def finish(p: _Pos, i: int, reason: str) -> None:
        nonlocal pos, cooldown_until
        pnl = cash - p.cash_before
        price_risk = p.qty0 * (p.entry - p.stop0)
        trades.append(
            TradeResult(
                strategy=p.signal.strategy,
                symbol=p.signal.symbol,
                entry_time=p.entry_time,
                exit_time=feats.time(i),
                entry_price=p.entry,
                exit_price=(p.exit_value / p.exit_qty) if p.exit_qty else p.entry,
                qty=p.qty0,
                pnl=pnl,
                fees=p.fees + p.qty0 * p.entry * fee,
                slippage=p.slip_cost,
                ret_pct=float(pnl / p.cash_before),
                pnl_r=float(pnl / price_risk) if price_risk > 0 else 0.0,
                bars_held=i - p.idx_open + 1,
                exit_reason=reason,
                score=p.score.score,
                reasons=p.signal.reasons,
            )
        )
        if gate is not None:
            gate.record_trade(pnl)
        if pnl < 0 and reason in ("stop", "breakeven", "trail"):
            cooldown_until = i + cooldown_bars
        pos = None

    for i in range(start, n):
        o, h, low, c = (dec(feats[k][i]) for k in ("open", "high", "low", "close"))

        # 1. entry scheduled by the previous bar's close fills at this bar's open
        if pending is not None and pos is None:
            sig, sc, rec = pending
            pending = None
            fill = o * (1 + slip)
            if fill <= sig.stop:
                rec.decision, rec.reason = Decision.REJECTED, "gapped below stop at entry"
            else:
                qty = ZERO_QTY
                reject = ""
                if gate is not None:
                    d = gate.decide(feats.time(i), cash, feats.symbol, fill, sig, sc.size_factor)
                    if d.approved:
                        qty = d.qty
                    else:
                        reject = "risk engine: " + ",".join(r.value for r in d.reasons)
                else:
                    unit_risk = (fill - sig.stop) + (fill + sig.stop) * (fee + slip)
                    qty = cash * cfg.risk_per_trade * sc.size_factor / unit_risk
                    qty = min(
                        qty, cash * cfg.max_symbol_exposure / fill, cash / (fill * (1 + fee))
                    ).quantize(QTY_STEP, rounding=ROUND_DOWN)
                    if qty * fill < cfg.min_notional:
                        reject = "below min notional"
                if reject:
                    rec.decision, rec.reason = Decision.REJECTED, reject
                else:
                    cash_before = cash
                    cash -= qty * fill * (1 + fee)
                    pos = _Pos(
                        signal=sig,
                        score=sc,
                        idx_open=i,
                        entry_time=feats.time(i),
                        entry=fill,
                        qty0=qty,
                        qty=qty,
                        stop=sig.stop,
                        stop0=sig.stop,
                        tp1_done=False,
                        highest=fill,
                        cash_before=cash_before,
                        slip_cost=qty * o * slip,
                    )

        # 2. manage the open position inside this bar (worst case first)
        if pos is not None:
            p = pos
            sig = p.signal
            if low <= p.stop:
                sell(p, p.qty, min(o, p.stop))
                finish(p, i, p.stop_kind)
            else:
                if sig.tp1 is not None and not p.tp1_done and h >= sig.tp1:
                    leg = min(p.qty, (p.qty0 * sig.tp1_close_fraction).quantize(QTY_STEP))
                    sell(p, leg, sig.tp1)
                    if p.qty <= 0:
                        finish(p, i, "tp1")
                    else:
                        p.tp1_done = True
                        p.stop = max(p.stop, p.entry * (1 + 2 * fee))  # breakeven + fees
                        p.stop_kind = "breakeven"
                        if low <= p.stop:  # bar also fell back to breakeven: take the exit
                            sell(p, p.qty, p.stop)
                            finish(p, i, "breakeven")
            p2 = pos  # finish() may have cleared it
            if p2 is not None:
                p = p2
                held = i - p.idx_open + 1
                if sig.false_breakout is not None and held <= sig.false_breakout[1]:
                    if c < sig.false_breakout[0]:
                        sell(p, p.qty, c)
                        finish(p, i, "false_breakout")
                p = pos
                if p is not None and sig.time_stop_bars is not None and held >= sig.time_stop_bars:
                    sell(p, p.qty, c)
                    finish(p, i, "time_stop")
                p = pos
                if p is not None and sig.trail is not None:
                    p.highest = max(p.highest, h)
                    if not sig.trail.after_tp1 or p.tp1_done:
                        atr_i = _atr_array(feats, sig.trail.period, atr_cache)[i]
                        if not np.isnan(atr_i):
                            level = p.highest - Decimal(repr(float(atr_i))) * Decimal(
                                repr(sig.trail.mult)
                            )
                            if level > p.stop:  # ratchets up only; applies from next bar
                                p.stop = level
                                p.stop_kind = "trail"

        # 3. last bar of the range: close out so every trade is realised
        if pos is not None and i == n - 1:
            sell(pos, pos.qty, c)
            finish(pos, i, "range_end")

        eq = cash + (pos.qty * c if pos is not None else Decimal(0))
        if gate is not None:
            gate.on_bar_close(feats.time(i) + timedelta(milliseconds=bar_ms), eq)
            if gate.kill_switch_active and pos is not None:  # kill switch: flatten
                sell(pos, pos.qty, c)
                finish(pos, i, "kill_switch")
                eq = cash
        equity_pts.append((feats.index[i], float(eq)))

        # 4. decide at the close of bar i (entry happens next bar)
        if pos is None and pending is None and i < n - 1:
            bd = decide_at_close(
                strategy, feats, i, cfg.weights, cfg.min_quote_volume_24h, i < cooldown_until
            )
            if bd is not None:
                rec2 = SignalRecord(bd.signal, bd.score, bd.decision, bd.reason)
                if bd.decision == Decision.TAKEN:
                    pending = (bd.signal, bd.score, rec2)
                records.append(rec2)

    idx = pd.DatetimeIndex([t for t, _ in equity_pts])
    return BacktestResult(
        strategy=strategy.name,
        symbol=feats.symbol,
        trades=trades,
        signals=records,
        equity=pd.Series([v for _, v in equity_pts], index=idx, dtype="float64"),
        initial_equity=start_cash,
        final_equity=cash,
        config=cfg,
    )
