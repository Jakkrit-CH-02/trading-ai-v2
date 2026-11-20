"""Walk-forward optimisation (SPEC 11.1): optimise on 12 months, test on the next 3, roll
forward by 3. Only the stitched **out-of-sample** result counts; in-sample numbers are shown
only to measure how much the optimiser flattered itself."""

import itertools
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from app.backtest.engine import BacktestConfig, TradeResult
from app.backtest.metrics import Metrics, compute_metrics
from app.backtest.registry import AnyStrategy, make_strategy, run_strategy
from app.strategies.base import MarketFrames
from app.strategies.features import Features


@dataclass(frozen=True, slots=True)
class WalkForwardConfig:
    train_months: int = 12
    test_months: int = 3
    step_months: int = 3
    min_train_trades: int = 10
    overfit_ratio: float = 1.5  # in-sample PF / out-of-sample PF above this => warning
    min_oos_trades_for_overfit: int = 30  # below this the ratio is noise; do not judge


@dataclass(slots=True)
class Fold:
    train_start: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    best_params: dict[str, Any]
    in_sample: Metrics
    out_of_sample: Metrics
    note: str = ""


@dataclass(slots=True)
class WalkForwardResult:
    folds: list[Fold]
    oos_trades: list[TradeResult]
    oos_equity: pd.Series
    oos_metrics: Metrics
    overfit_ratio: float | None
    warnings: list[str] = field(default_factory=list)


def _score(m: Metrics) -> float:
    pf = 10.0 if math.isinf(m.profit_factor) else m.profit_factor
    return pf + 1e-9 * m.net_pnl  # profit factor, ties broken by net PnL


def _capped_pf(m: Metrics) -> float:
    return 10.0 if math.isinf(m.profit_factor) else m.profit_factor


def walk_forward(
    name: str,
    data: MarketFrames,
    grid: Mapping[str, Sequence[Any]],
    cfg: BacktestConfig | None = None,
    wf: WalkForwardConfig | None = None,
) -> WalkForwardResult:
    cfg, wf = cfg or BacktestConfig(), wf or WalkForwardConfig()
    keys = sorted(grid)
    combos = [dict(zip(keys, v, strict=True)) for v in itertools.product(*(grid[k] for k in keys))]
    combos = combos or [{}]

    prepared: list[tuple[dict[str, Any], AnyStrategy, Features]] = []
    for combo in combos:
        strat = make_strategy(name, combo)
        prepared.append((combo, strat, strat.prepare(data)))
    index = prepared[0][2].index
    first, last = index[0], index[-1]

    def span(a: pd.Timestamp, b: pd.Timestamp) -> tuple[int, int]:
        return int(index.searchsorted(a, side="left")), int(index.searchsorted(b, side="left"))

    folds: list[Fold] = []
    oos_trades: list[TradeResult] = []
    equity_parts: list[pd.Series] = []
    equity = cfg.initial_equity
    start = first
    warnings: list[str] = []

    while True:
        test_start = start + pd.DateOffset(months=wf.train_months)
        test_end = test_start + pd.DateOffset(months=wf.test_months)
        if test_end > last + pd.Timedelta(days=1):
            break
        a, b = span(start, test_start)
        ranked: list[tuple[float, dict[str, Any], Metrics]] = []
        for combo, strat, feats in prepared:
            res = run_strategy(strat, feats, cfg, a, b)
            m = compute_metrics(res.trades, res.equity, float(res.initial_equity))
            if m.n_trades >= wf.min_train_trades:
                ranked.append((_score(m), combo, m))
        note = ""
        if ranked:
            _, best, is_m = max(ranked, key=lambda r: r[0])
        else:  # nothing traded enough in-sample: fall back to the first (default) combo
            best = combos[0]
            fres = run_strategy(prepared[0][1], prepared[0][2], cfg, a, b)
            is_m = compute_metrics(fres.trades, fres.equity, float(fres.initial_equity))
            note = f"fewer than {wf.min_train_trades} in-sample trades for every setting"
        _, strat, feats = next(p for p in prepared if p[0] == best)
        c, d = span(test_start, test_end)
        res = run_strategy(strat, feats, cfg, c, d, initial_equity=equity)
        oos_m = compute_metrics(res.trades, res.equity, float(res.initial_equity))
        equity = res.final_equity
        oos_trades.extend(res.trades)
        equity_parts.append(res.equity)
        folds.append(Fold(start, test_start, test_end, best, is_m, oos_m, note))
        start = start + pd.DateOffset(months=wf.step_months)

    if not folds:
        raise ValueError("not enough data for a single walk-forward fold")

    stitched = pd.concat(equity_parts)
    oos_metrics = compute_metrics(oos_trades, stitched, float(cfg.initial_equity))
    oos_pf = _capped_pf(oos_metrics)
    usable = [f for f in folds if not f.note and f.in_sample.n_trades >= wf.min_train_trades]
    ratio: float | None = None
    if oos_metrics.n_trades < wf.min_oos_trades_for_overfit or not usable:
        warnings.append(
            f"overfitting check skipped: fewer than {wf.min_oos_trades_for_overfit} "
            "out-of-sample trades (or in-sample trades) — too few to judge"
        )
    elif oos_pf > 0:
        ratio = (sum(_capped_pf(f.in_sample) for f in usable) / len(usable)) / oos_pf
        if ratio > wf.overfit_ratio:
            warnings.append(
                f"possible overfitting: mean in-sample profit factor is {ratio:.1f}x the "
                f"out-of-sample one (threshold {wf.overfit_ratio}x)"
            )
    if oos_pf < 1.0:
        warnings.append("out-of-sample profit factor is below 1.0 (losing money after costs)")
    return WalkForwardResult(folds, oos_trades, stitched, oos_metrics, ratio, warnings)
