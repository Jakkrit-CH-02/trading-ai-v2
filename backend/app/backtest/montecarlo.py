"""Robustness checks (SPEC 11.1): trade-order Monte Carlo and parameter perturbation."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

import numpy as np

from app.backtest.engine import TradeResult


@dataclass(frozen=True, slots=True)
class MonteCarloResult:
    runs: int
    max_dd_p50: float  # positive fractions, e.g. 0.18 = -18%
    max_dd_p95: float
    max_dd_worst: float
    final_return_p5: float
    final_return_p50: float


def monte_carlo(
    trades: Sequence[TradeResult], runs: int = 1000, seed: int = 0
) -> MonteCarloResult | None:
    """Shuffle trade order ``runs`` times and compound each trade's return on equity.

    Answers: how bad could the drawdown be with the same trades in an unlucky order?
    Returns None when there are too few trades to say anything.
    """
    returns = np.array([t.ret_pct for t in trades], dtype="float64")
    if len(returns) < 10:
        return None
    rng = np.random.default_rng(seed)
    order = np.stack([rng.permutation(len(returns)) for _ in range(runs)])
    curves = np.cumprod(1.0 + returns[order], axis=1)
    peaks = np.maximum.accumulate(np.concatenate([np.ones((runs, 1)), curves], axis=1), axis=1)[
        :, 1:
    ]
    dd = (1.0 - curves / peaks).max(axis=1)
    final = curves[:, -1] - 1.0
    return MonteCarloResult(
        runs=runs,
        max_dd_p50=float(np.percentile(dd, 50)),
        max_dd_p95=float(np.percentile(dd, 95)),
        max_dd_worst=float(dd.max()),
        final_return_p5=float(np.percentile(final, 5)),
        final_return_p50=float(np.percentile(final, 50)),
    )


@dataclass(frozen=True, slots=True)
class RobustnessResult:
    base_net_pnl: float
    variants: list[tuple[str, float, float]]  # (param, value, net_pnl)
    fraction_profitable: float


def param_robustness(
    base: dict[str, float],
    evaluate: Callable[[dict[str, float]], float],
    pct: float = 0.20,
) -> RobustnessResult:
    """Re-run with each numeric parameter moved by +/- ``pct`` and report how many variants
    stay profitable. A strategy that only works at one exact setting is overfit."""
    variants: list[tuple[str, float, float]] = []
    for key, value in base.items():
        for factor in (1 - pct, 1 + pct):
            v = value * factor
            if isinstance(value, int) and not isinstance(value, bool):
                v = max(1, round(v))
            variants.append((key, float(v), evaluate({**base, key: v})))
    profitable = sum(1 for _, _, pnl in variants if pnl > 0)
    return RobustnessResult(
        base_net_pnl=evaluate(base),
        variants=variants,
        fraction_profitable=profitable / len(variants) if variants else 0.0,
    )
