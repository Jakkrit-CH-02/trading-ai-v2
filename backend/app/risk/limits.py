"""Exposure limits (SPEC 3.2). Per-symbol exposure *reduces* size to fit; every other limit
*rejects* the trade. Each step is recorded so a rejection can be explained."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import Decimal

from app.risk.profile import RiskProfile
from app.risk.sizing import quantize_down
from app.risk.types import (
    ZERO,
    CheckResult,
    PortfolioState,
    Reason,
    SymbolFilters,
    TradeIntent,
)


@dataclass(slots=True)
class LimitOutcome:
    qty: Decimal
    checks: list[CheckResult] = field(default_factory=list)
    adjustments: list[str] = field(default_factory=list)

    @property
    def failed(self) -> list[CheckResult]:
        return [c for c in self.checks if not c.passed]


def apply_limits(
    intent: TradeIntent,
    qty: Decimal,
    portfolio: PortfolioState,
    buckets: Mapping[str, str],
    profile: RiskProfile,
    filters: SymbolFilters,
) -> LimitOutcome:
    out = LimitOutcome(qty)
    eq, entry = portfolio.equity, intent.entry

    def check(name: str, ok: bool, detail: str, reason: Reason) -> bool:
        out.checks.append(CheckResult(name, ok, detail, None if ok else reason))
        return ok

    # 1. number of open positions (adding to a symbol we already hold is not a new position)
    held = {p.symbol for p in portfolio.positions if p.qty > 0}
    is_new = intent.symbol not in held
    check(
        "max_positions",
        not (is_new and len(held) >= profile.max_positions),
        f"{len(held)} open, max {profile.max_positions}",
        Reason.MAX_POSITIONS,
    )

    # 2. per-symbol exposure: reduce to fit
    room = eq * profile.max_symbol_exposure - portfolio.symbol_notional(intent.symbol)
    if room <= 0:
        check(
            "symbol_exposure", False, "symbol already at its exposure cap", Reason.SYMBOL_EXPOSURE
        )
        out.qty = ZERO
        return out
    fit = quantize_down(room / entry, filters.step_size)
    if out.qty > fit:
        out.adjustments.append(
            f"qty {out.qty} -> {fit}: per-symbol exposure cap {profile.max_symbol_exposure:.0%}"
        )
        out.qty = fit
    check("symbol_exposure", out.qty > 0, f"room for {fit} units", Reason.SYMBOL_EXPOSURE)
    if out.qty <= 0:
        return out

    notional = out.qty * entry
    # 3. total exposure
    total_after = portfolio.total_exposure + notional
    check(
        "total_exposure",
        total_after <= eq * profile.max_total_exposure,
        f"{total_after / eq:.1%} of equity after, max {profile.max_total_exposure:.0%}",
        Reason.TOTAL_EXPOSURE,
    )

    # 4. open risk (distance to stop, all positions)
    new_risk = out.qty * (entry - intent.stop)
    risk_after = portfolio.open_risk + new_risk
    check(
        "open_risk",
        risk_after <= eq * profile.max_open_risk,
        f"{risk_after / eq:.2%} of equity after, max {profile.max_open_risk:.2%}",
        Reason.OPEN_RISK,
    )

    # 5. correlation bucket
    bucket = buckets.get(intent.symbol, intent.symbol)
    bucket_after = portfolio.bucket_open_risk(bucket, buckets) + new_risk
    check(
        "bucket_risk",
        bucket_after <= eq * profile.max_bucket_risk,
        f"bucket {bucket}: {bucket_after / eq:.2%} after, max {profile.max_bucket_risk:.2%}",
        Reason.BUCKET_RISK,
    )

    # 6. cash: can we pay, and does the USDT reserve survive?
    cost = notional * (1 + profile.fee_rate)
    check(
        "funds",
        cost <= portfolio.cash,
        f"need {cost:.2f}, have {portfolio.cash:.2f}",
        Reason.INSUFFICIENT_FUNDS,
    )
    reserve = eq * profile.min_cash_reserve
    check(
        "cash_reserve",
        portfolio.cash - cost >= reserve,
        f"{portfolio.cash - cost:.2f} left, reserve {reserve:.2f}",
        Reason.CASH_RESERVE,
    )
    return out
