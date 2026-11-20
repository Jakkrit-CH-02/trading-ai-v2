"""Backtest jobs for the Backtest Lab (SPEC 10 page 6). A job is a row in ``backtests``; the
runner executes one at a time in a worker thread (CPU bound) so the API stays responsive.
Results are JSON for the UI; only walk-forward out-of-sample numbers can pass gate 1."""

import math
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pandas as pd
from pydantic import BaseModel, Field, model_validator

from app.backtest.data import load_market_frames
from app.backtest.engine import BacktestConfig, FeeModel
from app.backtest.metrics import Metrics, compute_metrics, evaluate_gate1
from app.backtest.montecarlo import monte_carlo
from app.backtest.registry import make_strategy, run_strategy
from app.backtest.report import coverage_warning
from app.backtest.walkforward import WalkForwardResult, pool_walk_forward, walk_forward
from app.marketdata.store import CandleStore
from app.strategies.base import MarketFrames


class BacktestRequest(BaseModel):
    strategy: str = Field(pattern="^s[1-4]$")
    symbols: list[str] = Field(min_length=1, max_length=5)
    params: dict[str, float] = {}
    years: float = Field(3.0, ge=0.5, le=5.0)
    walk_forward: bool = True
    fee: float = Field(0.001, ge=0, le=0.01)
    slippage: float = Field(0.0005, ge=0, le=0.01)

    @model_validator(mode="after")
    def _check(self) -> "BacktestRequest":
        if len(self.symbols) > 1 and not self.walk_forward:
            raise ValueError("several symbols need walk_forward (pooled out-of-sample)")
        return self


def _num(x: float) -> float | None:
    return None if math.isinf(x) or math.isnan(x) else float(x)


def metrics_json(m: Metrics) -> dict[str, Any]:
    d = asdict(m)
    d["profit_factor"] = _num(m.profit_factor)
    d["yearly_returns"] = {str(k): v for k, v in m.yearly_returns.items()}
    return d


def _series(s: pd.Series, n: int = 300) -> list[list[float]]:
    s = s[~s.index.duplicated(keep="last")]
    if len(s) > n:
        s = s.iloc[:: math.ceil(len(s) / n)]
    return [[int(pd.Timestamp(str(t)).timestamp()), float(v)] for t, v in s.items()]


def _buy_hold(
    frames: dict[str, MarketFrames], index: pd.Index, initial: float
) -> list[list[float]]:
    """Equal-weight buy & hold of the same symbols over the out-of-sample window."""
    curves = []
    for fr in frames.values():
        close = fr.frames["1h"]["close"]
        close = close[(close.index >= index[0]) & (close.index <= index[-1])]
        if len(close):
            curves.append(close / close.iloc[0] * initial)
    if not curves:
        return []
    return _series(pd.concat(curves, axis=1).ffill().mean(axis=1))


def execute(frames: dict[str, MarketFrames], req: BacktestRequest) -> dict[str, Any]:
    """Synchronous and pure given the frames (this is what runs in the worker thread)."""
    cfg = BacktestConfig(
        fees=FeeModel(taker=Decimal(str(req.fee)), slippage=Decimal(str(req.slippage)))
    )
    initial = float(cfg.initial_equity)
    grid: dict[str, list[float]] = {k: [v] for k, v in req.params.items()}
    out: dict[str, Any] = {
        "walk_forward": req.walk_forward,
        "symbols": req.symbols,
        "warnings": [],
        "folds": [],
    }
    make_strategy(req.strategy, req.params)  # fail early on unknown/invalid parameters

    if req.walk_forward:
        results: dict[str, WalkForwardResult] = {}
        for sym, data in frames.items():
            try:
                results[sym] = walk_forward(req.strategy, data, grid, cfg)
            except ValueError as e:
                out["warnings"].append(f"{sym}: skipped ({e})")
        if not results:
            raise ValueError("no symbol had enough data for walk-forward")
        trades, equity, metrics = pool_walk_forward(list(results.values()), initial)
        for sym, r in results.items():
            for f in r.folds:
                out["folds"].append(
                    {
                        "symbol": sym,
                        "test_start": f.test_start.isoformat(),
                        "test_end": f.test_end.isoformat(),
                        "params": f.best_params,
                        "is_pf": _num(f.in_sample.profit_factor),
                        "oos_pf": _num(f.out_of_sample.profit_factor),
                        "oos_trades": f.out_of_sample.n_trades,
                        "note": f.note,
                    }
                )
            out["warnings"].extend(f"{sym}: {w}" for w in r.warnings)
        ratios = [r.overfit_ratio for r in results.values() if r.overfit_ratio is not None]
        out["overfit_ratio"] = max(ratios) if ratios else None
    else:
        ((sym, data),) = frames.items()
        strategy = make_strategy(req.strategy, req.params)
        res = run_strategy(strategy, strategy.prepare(data), cfg)
        trades, equity = res.trades, res.equity
        metrics = compute_metrics(res.trades, res.equity, float(res.initial_equity))
        out["warnings"].append("single in-sample run: NOT out-of-sample, cannot pass gate 1")
        out["overfit_ratio"] = None

    cov = min(
        (coverage_warning(fr.frames["1h"].index) for fr in frames.values()), key=lambda w: w is None
    )
    if cov:
        out["warnings"].append(cov)
    gate = evaluate_gate1(metrics)
    out["metrics"] = metrics_json(metrics)
    out["gate1"] = {"passed": gate.passed and req.walk_forward, "failures": gate.failures}
    if not req.walk_forward:
        out["gate1"]["failures"] = ["not a walk-forward run", *gate.failures]
    mc = monte_carlo(trades)
    out["monte_carlo"] = asdict(mc) if mc else None
    if len(equity):
        out["equity"] = _series(equity)
        out["buy_hold"] = _buy_hold(frames, equity.index, initial)
    else:
        out["equity"], out["buy_hold"] = [], []
    return out


async def load_frames(
    store: CandleStore, symbols: list[str], years: float
) -> dict[str, MarketFrames]:
    end = datetime.now(UTC)
    start = end - timedelta(days=int(years * 365.25))
    return {s: await load_market_frames(store, s, start, end) for s in symbols}
