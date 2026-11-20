"""Risk Engine: the only component allowed to approve an order and the only one that sets
its size (SPEC principle 1). Strategies, the AI and humans (manual orders) all pass through
``RiskEngine.evaluate``; there is no other path to the order manager.

``evaluate`` is deterministic: same inputs, same decision. It never raises on bad business
input — it returns a rejection with reasons — so a caller cannot "forget" to handle one.
"""

from dataclasses import replace
from decimal import ROUND_DOWN, Decimal
from typing import Any

from app.core.models import BotStatus, Side
from app.risk.breakers import BreakerKind, CircuitBreakers
from app.risk.limits import apply_limits
from app.risk.profile import RiskProfile
from app.risk.sizing import effective_risk_pct, position_size, quantize_down, unit_risk
from app.risk.types import (
    ZERO,
    CheckResult,
    MarketState,
    PortfolioState,
    Reason,
    RiskDecision,
    SymbolFilters,
    TradeIntent,
)

_RUNNING = (BotStatus.RUNNING, BotStatus.PAPER)


def round_price(price: Decimal, tick: Decimal) -> Decimal:
    """Round *down* to the tick (cheaper buy limit, wider stop, smaller target: never riskier)."""
    return (price / tick).to_integral_value(rounding=ROUND_DOWN) * tick


class RiskEngine:
    def __init__(self, profile: RiskProfile, breakers: CircuitBreakers | None = None) -> None:
        self.profile = profile
        self.breakers = breakers or CircuitBreakers(profile)

    # ---- helpers ------------------------------------------------------------------------

    def _reject(
        self, checks: list[CheckResult], adjustments: list[str] | None = None
    ) -> RiskDecision:
        reasons = tuple(dict.fromkeys(c.reason for c in checks if not c.passed and c.reason))
        return RiskDecision(
            False, ZERO, ZERO, ZERO, reasons, tuple(checks), tuple(adjustments or ())
        )

    # ---- the checklist (SPEC 3.5) -------------------------------------------------------

    def evaluate(
        self,
        intent: TradeIntent,
        portfolio: PortfolioState,
        market: MarketState,
        filters: SymbolFilters,
        kelly: Decimal | None = None,
    ) -> RiskDecision:
        p = self.profile
        checks: list[CheckResult] = []

        def check(name: str, ok: bool, detail: str, reason: Reason) -> bool:
            checks.append(CheckResult(name, ok, detail, None if ok else reason))
            return ok

        # 0. sanity: refuse garbage rather than size it
        if intent.side != Side.BUY:
            check("side", False, "only long spot entries are supported", Reason.SHORT_NOT_SUPPORTED)
            return self._reject(checks)
        entry = (
            round_price(intent.entry, filters.tick_size) if filters.tick_size > 0 else intent.entry
        )
        stop = round_price(intent.stop, filters.tick_size) if filters.tick_size > 0 else intent.stop
        tp1 = (
            round_price(intent.tp1, filters.tick_size)
            if intent.tp1 is not None and filters.tick_size > 0
            else intent.tp1
        )
        sane = (
            entry > 0
            and portfolio.equity > 0
            and filters.step_size > 0
            and intent.size_factor > 0
            and intent.regime_factor > 0
        )
        if not check(
            "input", sane, "positive prices/equity/factors required", Reason.INVALID_INPUT
        ):
            if intent.size_factor <= 0:
                checks.append(
                    CheckResult("score", False, "score factor 0: skipped", Reason.SCORE_SKIP)
                )
            return self._reject(checks)

        # fresh breaker state: loss limits are re-evaluated on every decision
        self.breakers.observe_equity(market.now, portfolio)
        active = self.breakers.active(market.now)

        # 1. bot state and breakers
        check(
            "bot_running",
            market.bot_status in _RUNNING,
            f"status {market.bot_status}",
            Reason.BOT_NOT_RUNNING,
        )
        kill = [b for b in active if b.kind == BreakerKind.KILL_SWITCH]
        check("kill_switch", not kill, kill[0].detail if kill else "off", Reason.KILL_SWITCH)
        others = [b for b in active if b.kind != BreakerKind.KILL_SWITCH]
        check(
            "circuit_breakers",
            not others,
            ", ".join(f"{b.kind}: {b.detail}" for b in others) or "none active",
            Reason.BREAKER_ACTIVE,
        )

        # 2. data freshness and clock
        check(
            "data_fresh",
            market.data_age_s < p.max_data_age_s,
            f"age {market.data_age_s:.1f}s, max {p.max_data_age_s}s",
            Reason.STALE_DATA,
        )
        check(
            "clock_drift",
            market.clock_drift_ms < p.max_clock_drift_ms,
            f"{market.clock_drift_ms:.0f}ms, max {p.max_clock_drift_ms:.0f}ms",
            Reason.CLOCK_DRIFT,
        )

        # 3. stop loss exists on the right side, target exists, R:R after costs
        stop_ok = stop > 0 and stop < entry
        check(
            "stop_loss",
            stop_ok,
            f"entry {entry}, stop {stop}",
            Reason.NO_STOP if stop <= 0 else Reason.BAD_STOP_SIDE,
        )
        if stop_ok:
            if tp1 is None or tp1 <= entry:
                check(
                    "risk_reward",
                    False,
                    "no valid target: R:R cannot be verified",
                    Reason.NO_TARGET,
                )
            else:
                ur = unit_risk(entry, stop, p.fee_rate, p.slippage_rate)
                reward = (tp1 - entry) - (entry + tp1) * (p.fee_rate + p.slippage_rate)
                rr = reward / ur if ur > 0 else ZERO
                check(
                    "risk_reward",
                    rr >= p.min_rr,
                    f"R:R {rr:.2f} after costs, min {p.min_rr}",
                    Reason.RR_TOO_LOW,
                )

        # 4. order-type rules: market orders need a slippage estimate (and may be forbidden)
        if intent.order_type == "MARKET":
            if self.breakers.force_limit_orders:
                check(
                    "order_type",
                    False,
                    "average slippage too high: limit orders enforced",
                    Reason.SLIPPAGE,
                )
            elif intent.expected_slippage_bps is None:
                check(
                    "slippage",
                    False,
                    "market order without a depth-based slippage estimate",
                    Reason.MARKET_ORDER_NO_DEPTH,
                )
            else:
                check(
                    "slippage",
                    intent.expected_slippage_bps <= p.max_slippage_bps,
                    f"{intent.expected_slippage_bps} bps, max {p.max_slippage_bps}",
                    Reason.SLIPPAGE,
                )

        # 5. blackout and cooldown
        check(
            "event_blackout",
            not market.blackout,
            "news blackout" if market.blackout else "clear",
            Reason.BLACKOUT,
        )
        until = market.cooldowns.get(intent.symbol)
        check(
            "cooldown",
            until is None or market.now >= until,
            f"until {until}" if until else "none",
            Reason.COOLDOWN,
        )

        if any(not c.passed for c in checks):
            return self._reject(checks)

        # 6. size, then exposure limits, then exchange filters
        risk_pct = effective_risk_pct(p, self.breakers.risk_multiplier, kelly)
        sized = position_size(
            portfolio.equity,
            risk_pct,
            intent.regime_factor,
            intent.size_factor,
            entry,
            stop,
            filters,
            p,
        )
        adjustments: list[str] = []
        if self.breakers.risk_multiplier != 1:
            adjustments.append(f"risk halved after a losing streak ({risk_pct:.3%} of equity)")
        # limits must be judged on the *same* tick-rounded prices the order will use; judging
        # them on the raw prices under-counted risk when rounding widened the stop
        priced = replace(intent, entry=entry, stop=stop, tp1=tp1)
        limited = apply_limits(priced, sized.qty, portfolio, market.buckets, p, filters)
        checks.extend(limited.checks)
        adjustments.extend(limited.adjustments)
        qty = quantize_down(limited.qty, filters.step_size)

        ok_qty = check(
            "min_qty",
            qty >= filters.min_qty and qty > 0,
            f"qty {qty}, min {filters.min_qty}",
            Reason.BELOW_MIN_QTY,
        )
        ok_notional = check(
            "min_notional",
            qty * entry >= filters.min_notional,
            f"{qty * entry:.2f}, min {filters.min_notional}",
            Reason.BELOW_MIN_NOTIONAL,
        )
        if any(not c.passed for c in checks) or not (ok_qty and ok_notional):
            return self._reject(checks, adjustments)

        return RiskDecision(
            approved=True,
            qty=qty,
            notional=qty * entry,
            risk_amount=qty * (entry - stop),
            reasons=(),
            checks=tuple(checks),
            adjustments=tuple(adjustments),
            entry=entry,
            stop=stop,
            tp1=tp1,
        )


def decision_payload(intent: TradeIntent, d: RiskDecision) -> dict[str, Any]:
    """JSON-safe record for the ``risk_events`` / ``signals`` tables (money as strings)."""
    return {
        "symbol": intent.symbol,
        "strategy": intent.strategy,
        "signal_id": intent.signal_id,
        "manual": intent.is_manual,
        "approved": d.approved,
        "qty": str(d.qty),
        "reasons": [r.value for r in d.reasons],
        "checks": [{"name": c.name, "passed": c.passed, "detail": c.detail} for c in d.checks],
        "adjustments": list(d.adjustments),
    }
