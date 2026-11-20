"""Position sizing (SPEC 3.1):

    Qty = Equity x Risk% x RegimeFactor x ScoreFactor / (|Entry - SL| + Fees + Slippage)

All amounts are per unit of the base asset. Quantities are always rounded *down* to the
exchange step so rounding can only make a position smaller, never riskier.
"""

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal

from app.risk.profile import RiskProfile
from app.risk.types import ZERO, SymbolFilters


def quantize_down(x: Decimal, step: Decimal) -> Decimal:
    if step <= 0:
        raise ValueError("step must be positive")
    return (x / step).to_integral_value(rounding=ROUND_DOWN) * step


def unit_risk(entry: Decimal, stop: Decimal, fee_rate: Decimal, slippage_rate: Decimal) -> Decimal:
    """Loss per unit if stopped out: price distance + round-trip fees + slippage on both legs."""
    return abs(entry - stop) + (entry + stop) * (fee_rate + slippage_rate)


def kelly_fraction(win_rate: Decimal, payoff_ratio: Decimal) -> Decimal:
    """Full Kelly f* = W - (1-W)/R. Used only as a ceiling, never to size directly."""
    if payoff_ratio <= 0:
        return ZERO
    return max(ZERO, win_rate - (Decimal(1) - win_rate) / payoff_ratio)


def effective_risk_pct(
    profile: RiskProfile,
    multiplier: Decimal = Decimal(1),
    kelly: Decimal | None = None,
) -> Decimal:
    """Base risk %, scaled by the loss-streak multiplier, capped by 1/4 Kelly and the SPEC cap."""
    pct = profile.risk_per_trade * multiplier
    if kelly is not None:
        pct = min(pct, kelly * profile.kelly_cap_fraction)
    return max(ZERO, min(pct, profile.risk_per_trade_cap))


@dataclass(frozen=True, slots=True)
class SizeResult:
    qty: Decimal  # rounded down to step_size; 0 if nothing valid fits
    risk_amount: Decimal  # budget: equity x risk% x factors
    unit_risk: Decimal
    notional: Decimal


def position_size(
    equity: Decimal,
    risk_pct: Decimal,
    regime_factor: Decimal,
    score_factor: Decimal,
    entry: Decimal,
    stop: Decimal,
    filters: SymbolFilters,
    profile: RiskProfile,
) -> SizeResult:
    if equity <= 0 or entry <= 0 or stop <= 0 or risk_pct <= 0:
        return SizeResult(ZERO, ZERO, ZERO, ZERO)
    if regime_factor <= 0 or score_factor <= 0:
        return SizeResult(ZERO, ZERO, ZERO, ZERO)
    risk_amount = equity * risk_pct * regime_factor * score_factor
    ur = unit_risk(entry, stop, profile.fee_rate, profile.slippage_rate)
    if ur <= 0:
        return SizeResult(ZERO, risk_amount, ur, ZERO)
    qty = min(quantize_down(risk_amount / ur, filters.step_size), filters.max_qty)
    qty = quantize_down(qty, filters.step_size)
    return SizeResult(qty, risk_amount, ur, qty * entry)
