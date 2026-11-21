"""Paper-vs-backtest comparison (SPEC 11.2, gate 2): the same config is backtested over exactly
the window the bot has been paper trading, and the two results are compared in R multiples."""

import asyncio
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from app.backtest.data import load_market_frames
from app.backtest.engine import BacktestConfig
from app.backtest.registry import run_strategy
from app.marketdata.store import CandleStore
from app.runtime.runner import UNSUPPORTED, build_strategy

WARMUP = timedelta(
    days=260
)  # indicators need history before the window; trades before it are dropped
DEVIATION_FLOOR_R = 1.0  # a backtest of < 1R total is compared against 1R, not noise


@dataclass(frozen=True, slots=True)
class PaperComparison:
    deviation: float | None  # None = not enough data to judge
    paper_r: float
    backtest_r: float | None
    backtest_trades: int
    detail: str


def deviation(paper_r: float, backtest_r: float) -> float:
    return abs(paper_r - backtest_r) / max(abs(backtest_r), DEVIATION_FLOOR_R)


async def backtest_r(
    candles: CandleStore,
    strategy: str,
    params: dict[str, Any],
    symbols: list[str],
    start: datetime,
    end: datetime,
    cfg: BacktestConfig | None = None,
) -> tuple[float, int]:
    """Total R and trade count of the backtest for trades that *opened* inside [start, end].
    A trade still open at ``end`` is dropped (paper's open position is not a closed trade)."""
    cfg = cfg or BacktestConfig()
    if strategy in UNSUPPORTED:
        raise ValueError(f"{strategy} is not run live")
    total, n = 0.0, 0
    for symbol in symbols:
        frames = await load_market_frames(candles, symbol, start - WARMUP, end)
        strat = build_strategy(strategy, params)
        feats = await asyncio.to_thread(strat.prepare, frames)
        res = await asyncio.to_thread(run_strategy, strat, feats, cfg)
        for t in res.trades:
            if t.entry_time >= start and t.exit_reason != "range_end":
                total += t.pnl_r
                n += 1
    return total, n


async def compare(
    candles: CandleStore,
    strategy: str,
    params: dict[str, Any],
    symbols: list[str],
    start: datetime,
    end: datetime,
    paper_r: float,
    cfg: BacktestConfig | None = None,
) -> PaperComparison:
    try:
        bt, n = await backtest_r(candles, strategy, params, symbols, start, end, cfg)
    except ValueError as e:  # no candles for the window / unsupported strategy
        return PaperComparison(None, paper_r, None, 0, str(e))
    if n == 0:
        return PaperComparison(
            None, paper_r, bt, 0, "the backtest of the same window has no closed trades yet"
        )
    d = deviation(paper_r, bt)
    return PaperComparison(
        d, paper_r, bt, n, f"paper {paper_r:+.2f}R vs backtest {bt:+.2f}R ({n} trades)"
    )
