"""Backtest statistics and the SPEC 11.2 gate-1 criteria. Statistics are analytics, so they
use float; the ledger itself stays Decimal."""

import math
from collections.abc import Sequence
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from app.backtest.engine import TradeResult


@dataclass(frozen=True, slots=True)
class Metrics:
    n_trades: int
    win_rate: float
    profit_factor: float  # inf when there are no losing trades
    expectancy_r: float
    net_pnl: float
    total_return: float
    max_drawdown: float  # positive fraction, e.g. 0.12 = -12%
    sharpe: float  # daily equity returns, annualised with sqrt(365)
    worst_year_return: float
    yearly_returns: dict[int, float] = field(default_factory=dict)
    fees_paid: float = 0.0


def compute_metrics(
    trades: Sequence[TradeResult], equity: pd.Series, initial_equity: float
) -> Metrics:
    pnls = np.array([float(t.pnl) for t in trades], dtype="float64")
    rs = np.array([t.pnl_r for t in trades], dtype="float64")
    wins, losses = pnls[pnls > 0].sum(), -pnls[pnls < 0].sum()
    pf = float(wins / losses) if losses > 0 else (math.inf if wins > 0 else 0.0)

    if len(equity):
        dd = float((1 - equity / equity.cummax()).max())
        end_eq = float(equity.iloc[-1])
        daily = equity.resample("1D").last().ffill()
        r = daily.pct_change().dropna()
        sharpe = (
            float(r.mean() / r.std(ddof=1) * math.sqrt(365)) if len(r) > 2 and r.std() > 0 else 0.0
        )
        year_end = equity.resample("YE").last()
        starts = pd.concat([pd.Series([initial_equity]), year_end.iloc[:-1]]).to_numpy()
        yearly = {
            int(ts.year): float(v / s - 1)
            for ts, v, s in zip(year_end.index, year_end, starts, strict=True)
        }
    else:
        dd, end_eq, sharpe, yearly = 0.0, initial_equity, 0.0, {}

    return Metrics(
        n_trades=len(trades),
        win_rate=float((pnls > 0).mean()) if len(pnls) else 0.0,
        profit_factor=pf,
        expectancy_r=float(rs.mean()) if len(rs) else 0.0,
        net_pnl=float(pnls.sum()),
        total_return=end_eq / initial_equity - 1,
        max_drawdown=dd,
        sharpe=sharpe,
        worst_year_return=min(yearly.values()) if yearly else 0.0,
        yearly_returns=yearly,
        fees_paid=float(sum(float(t.fees) for t in trades)),
    )


@dataclass(frozen=True, slots=True)
class Gate1Criteria:
    """SPEC 11.2 gate 1 (out-of-sample, after costs). Do not loosen to make a strategy pass."""

    min_trades: int = 100
    min_profit_factor: float = 1.3
    min_sharpe: float = 1.0
    max_drawdown: float = 0.20
    min_expectancy_r: float = 0.15
    max_year_loss: float = 0.10


@dataclass(frozen=True, slots=True)
class GateResult:
    passed: bool
    failures: list[str]


def evaluate_gate1(m: Metrics, c: Gate1Criteria | None = None) -> GateResult:
    c = c or Gate1Criteria()
    checks = [
        (m.n_trades >= c.min_trades, f"trades {m.n_trades} < {c.min_trades}"),
        (
            m.profit_factor >= c.min_profit_factor,
            f"profit factor {m.profit_factor:.2f} < {c.min_profit_factor}",
        ),
        (m.sharpe >= c.min_sharpe, f"sharpe {m.sharpe:.2f} < {c.min_sharpe}"),
        (
            m.max_drawdown <= c.max_drawdown,
            f"max drawdown {m.max_drawdown:.1%} > {c.max_drawdown:.0%}",
        ),
        (
            m.expectancy_r > c.min_expectancy_r,
            f"expectancy {m.expectancy_r:.2f}R <= {c.min_expectancy_r}R",
        ),
        (
            m.worst_year_return >= -c.max_year_loss,
            f"worst year {m.worst_year_return:.1%} < -{c.max_year_loss:.0%}",
        ),
    ]
    failures = [msg for ok, msg in checks if not ok]
    return GateResult(not failures, failures)
