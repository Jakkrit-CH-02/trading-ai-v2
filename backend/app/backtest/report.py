"""Plain-text backtest report. Honest by construction: shows costs, trade count, and every
gate-1 criterion that failed; never rounds a failure into a pass."""

import math

import pandas as pd

from app.backtest.metrics import GateResult, Metrics
from app.backtest.montecarlo import MonteCarloResult
from app.backtest.walkforward import WalkForwardResult


def _pf(x: float) -> str:
    return "inf" if math.isinf(x) else f"{x:.2f}"


def format_metrics(m: Metrics) -> str:
    years = ", ".join(f"{y}: {r:+.1%}" for y, r in sorted(m.yearly_returns.items())) or "-"
    return (
        f"  trades            {m.n_trades}\n"
        f"  win rate          {m.win_rate:.1%}\n"
        f"  profit factor     {_pf(m.profit_factor)}\n"
        f"  expectancy        {m.expectancy_r:+.2f} R\n"
        f"  net PnL           {m.net_pnl:+,.2f} USDT  ({m.total_return:+.1%})\n"
        f"  max drawdown      {m.max_drawdown:.1%}\n"
        f"  sharpe (daily)    {m.sharpe:.2f}\n"
        f"  fees paid         {m.fees_paid:,.2f} USDT\n"
        f"  yearly            {years}"
    )


def format_gate(g: GateResult) -> str:
    if g.passed:
        return "  GATE 1 (SPEC 11.2): PASS"
    return "  GATE 1 (SPEC 11.2): FAIL\n" + "\n".join(f"    - {f}" for f in g.failures)


def format_monte_carlo(mc: MonteCarloResult | None) -> str:
    if mc is None:
        return "  monte carlo       skipped (fewer than 10 trades)"
    return (
        f"  monte carlo       {mc.runs} shuffles: max DD median {mc.max_dd_p50:.1%}, "
        f"p95 {mc.max_dd_p95:.1%}, worst {mc.max_dd_worst:.1%}; "
        f"final return p5 {mc.final_return_p5:+.1%}"
    )


def coverage_warning(index: pd.Index, min_years: float = 3.0) -> str | None:
    if len(index) < 2:
        return "no data"
    days = (index[-1] - index[0]).days + 1
    if days < min_years * 365:
        return (
            f"only {days / 365:.1f} years of data; SPEC 11.1 requires >= {min_years:.0f} years, "
            "so this run cannot pass gate 1"
        )
    return None


def format_walk_forward(w: WalkForwardResult) -> str:
    lines = ["  fold  test window                 params                 IS PF  OOS PF  OOS trades"]
    for k, f in enumerate(w.folds, 1):
        win = f"{f.test_start:%Y-%m-%d} -> {f.test_end:%Y-%m-%d}"
        params = ",".join(f"{a}={b}" for a, b in f.best_params.items()) or "default"
        lines.append(
            f"  {k:>4}  {win}  {params:<22} {_pf(f.in_sample.profit_factor):>5}  "
            f"{_pf(f.out_of_sample.profit_factor):>6}  {f.out_of_sample.n_trades:>10}"
            + (f"  ({f.note})" if f.note else "")
        )
    lines.append("")
    lines.append("  OUT-OF-SAMPLE (stitched) — the only numbers that count:")
    lines.append(format_metrics(w.oos_metrics))
    for warn in w.warnings:
        lines.append(f"  WARNING: {warn}")
    return "\n".join(lines)
