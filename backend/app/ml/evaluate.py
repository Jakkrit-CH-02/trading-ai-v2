"""From candles to a trained model, and the question that matters: does S_ml improve the
strategy out of sample?

``compare_backtests`` runs the strategy twice over the *same* out-of-fold period: once with
S_ml = 50 (today's behaviour) and once with S_ml taken from out-of-fold predictions - the model
that was trained only on the past of each bar. If the second run is not better, the model does
not go live, whatever its AUC says.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pandas as pd

from app.backtest.engine import BacktestConfig, TradeResult, run_backtest
from app.backtest.metrics import Metrics, compute_metrics
from app.backtest.registry import AnyStrategy, make_strategy
from app.backtest.walkforward import WalkForwardResult, pool_walk_forward
from app.ml.features import with_ml_features
from app.ml.labels import build_dataset
from app.ml.scorer import NEUTRAL, p_to_score
from app.strategies.base import MarketFrames, Strategy
from app.strategies.features import Features
from app.strategies.types import Signal

MIN_TRADES = 60  # fewer out-of-sample trades than this cannot show an improvement
MIN_GAIN_R = 0.05  # required improvement in expectancy (R per trade) before ML may go live


@dataclass(slots=True)
class Prepared:
    symbol: str
    strategy: Strategy
    feats: Features


def prepare_symbols(name: str, frames: Mapping[str, MarketFrames]) -> list[Prepared]:
    strat: AnyStrategy = make_strategy(name)
    if not hasattr(strat, "evaluate"):
        raise ValueError(f"{name} has no entry signals to learn from (grid strategy)")
    out = []
    for sym, data in frames.items():
        base = strat.prepare(data)
        out.append(Prepared(sym, strat, with_ml_features(base, data)))
    return out


def build_all(prepared: list[Prepared]) -> pd.DataFrame:
    parts = [build_dataset(p.strategy.evaluate, p.feats, p.symbol) for p in prepared]
    df = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    return df.sort_values("t").reset_index(drop=True)


@dataclass(slots=True)
class Comparison:
    baseline: Metrics
    with_ml: Metrics
    n_trades_changed: int  # signals whose TAKEN/SKIPPED fate differs between the two runs
    period: tuple[pd.Timestamp, pd.Timestamp]
    n_symbols: int


def _pool(per_symbol: list[tuple[list[TradeResult], pd.Series]], initial: float) -> Metrics:
    results = [
        WalkForwardResult([], tr, eq, compute_metrics(tr, eq, initial), None)
        for tr, eq in per_symbol
    ]
    _, _, m = pool_walk_forward(results, initial)
    return m


def compare_backtests(
    prepared: list[Prepared], oof: pd.DataFrame, base_rate: float, cfg: BacktestConfig | None = None
) -> Comparison:
    cfg = cfg or BacktestConfig()
    initial = float(cfg.initial_equity)
    lookup: dict[tuple[str, pd.Timestamp], float] = {
        (str(sym), pd.Timestamp(t)): float(p)
        for sym, t, p in zip(oof["symbol"], oof["t"], oof["p"], strict=True)
    }
    start_t = oof["t"].min()

    def ml_score(feats: Features, i: int, sig: Signal) -> float:
        p = lookup.get((feats.symbol, feats.index[i]))
        return NEUTRAL if p is None else p_to_score(p, base_rate)

    base_runs, ml_runs, changed = [], [], 0
    for p in prepared:
        a = int(p.feats.index.searchsorted(start_t))
        base = run_backtest(p.strategy, p.feats, cfg, a, None, Decimal(cfg.initial_equity))
        withml = run_backtest(
            p.strategy, p.feats, cfg, a, None, Decimal(cfg.initial_equity), ml_score
        )
        base_runs.append((base.trades, base.equity))
        ml_runs.append((withml.trades, withml.equity))
        fate = {r.signal.bar_time: r.decision for r in base.signals}
        changed += sum(
            1 for r in withml.signals if fate.get(r.signal.bar_time) not in (None, r.decision)
        )
    return Comparison(
        baseline=_pool(base_runs, initial),
        with_ml=_pool(ml_runs, initial),
        n_trades_changed=changed,
        period=(start_t, max(p.feats.index[-1] for p in prepared)),
        n_symbols=len(prepared),
    )


def verdict(c: Comparison) -> tuple[bool, str]:
    """Does ML improve the out-of-sample backtest? Requires enough trades to say anything."""
    b, m = c.baseline, c.with_ml
    if min(b.n_trades, m.n_trades) < MIN_TRADES:
        return False, f"too few trades to judge ({b.n_trades} baseline, {m.n_trades} with ML)"
    # ~100 trades have a standard error of ~0.1R: a smaller gain is indistinguishable from luck
    better = m.expectancy_r >= b.expectancy_r + MIN_GAIN_R and m.net_pnl >= b.net_pnl
    return better, (
        f"expectancy {b.expectancy_r:+.3f}R -> {m.expectancy_r:+.3f}R, "
        f"net PnL {b.net_pnl:+.0f} -> {m.net_pnl:+.0f}, trades {b.n_trades} -> {m.n_trades}"
    )


def metrics_line(m: Metrics) -> dict[str, Any]:
    return {
        "trades": m.n_trades,
        "win_rate": round(m.win_rate, 3),
        "profit_factor": None if m.profit_factor == float("inf") else round(m.profit_factor, 3),
        "expectancy_r": round(m.expectancy_r, 3),
        "net_pnl": round(m.net_pnl, 2),
        "max_drawdown": round(m.max_drawdown, 3),
    }
