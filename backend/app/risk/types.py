"""Risk Engine data types. Everything monetary is ``Decimal``; time is passed in explicitly
(``now``) so every decision is reproducible and testable."""

import enum
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.core.models import BotStatus, Side

ZERO = Decimal(0)


class Reason(enum.StrEnum):
    """Machine-readable reject codes (stored in ``risk_events`` / ``signals.reject_reason``)."""

    INVALID_INPUT = "INVALID_INPUT"
    SHORT_NOT_SUPPORTED = "SHORT_NOT_SUPPORTED"
    SCORE_SKIP = "SCORE_SKIP"
    BOT_NOT_RUNNING = "BOT_NOT_RUNNING"
    BREAKER_ACTIVE = "BREAKER_ACTIVE"
    KILL_SWITCH = "KILL_SWITCH"
    STALE_DATA = "STALE_DATA"
    CLOCK_DRIFT = "CLOCK_DRIFT"
    NO_STOP = "NO_STOP"
    BAD_STOP_SIDE = "BAD_STOP_SIDE"
    NO_TARGET = "NO_TARGET"
    RR_TOO_LOW = "RR_TOO_LOW"
    MAX_POSITIONS = "MAX_POSITIONS"
    SYMBOL_EXPOSURE = "SYMBOL_EXPOSURE"
    TOTAL_EXPOSURE = "TOTAL_EXPOSURE"
    OPEN_RISK = "OPEN_RISK"
    BUCKET_RISK = "BUCKET_RISK"
    CASH_RESERVE = "CASH_RESERVE"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    BELOW_MIN_QTY = "BELOW_MIN_QTY"
    BELOW_MIN_NOTIONAL = "BELOW_MIN_NOTIONAL"
    BLACKOUT = "BLACKOUT"
    COOLDOWN = "COOLDOWN"
    SLIPPAGE = "SLIPPAGE"
    MARKET_ORDER_NO_DEPTH = "MARKET_ORDER_NO_DEPTH"


@dataclass(frozen=True, slots=True)
class SymbolFilters:
    """Binance symbol filters (PRICE_FILTER, LOT_SIZE, MIN_NOTIONAL)."""

    tick_size: Decimal
    step_size: Decimal
    min_qty: Decimal
    max_qty: Decimal
    min_notional: Decimal


@dataclass(frozen=True, slots=True)
class TradeIntent:
    """What a strategy / the AI / a human *wants*: a direction and a stop. How much to trade
    is decided only by the Risk Engine (SPEC 3)."""

    symbol: str
    side: Side
    entry: Decimal  # reference price
    stop: Decimal
    strategy: str = "manual"
    tp1: Decimal | None = None
    order_type: str = "LIMIT"  # "LIMIT" | "MARKET"
    size_factor: Decimal = Decimal(1)  # ScoreFactor from scoring: 1, 0.5 (0 = skip)
    regime_factor: Decimal = Decimal(1)  # 1, or 0.5 in HIGH_VOL
    signal_id: str | None = None
    bot_id: str | None = None
    is_manual: bool = False
    expected_slippage_bps: Decimal | None = None  # from order-book depth, for MARKET orders


@dataclass(frozen=True, slots=True)
class PositionView:
    symbol: str
    qty: Decimal
    avg_entry: Decimal
    mark_price: Decimal
    stop: Decimal | None  # None = unprotected (treated as the worst case)

    @property
    def notional(self) -> Decimal:
        return self.qty * self.mark_price

    @property
    def open_risk(self) -> Decimal:
        """Loss if the stop is hit now. No stop = full notional (conservative)."""
        if self.stop is None:
            return self.notional
        return max(ZERO, self.qty * (self.mark_price - self.stop))


@dataclass(frozen=True, slots=True)
class PortfolioState:
    equity: Decimal  # cash + marked positions, USDT
    cash: Decimal  # free USDT
    peak_equity: Decimal
    day_start_equity: Decimal  # 00:00 UTC
    week_start_equity: Decimal
    positions: tuple[PositionView, ...] = ()

    def symbol_notional(self, symbol: str) -> Decimal:
        return sum((p.notional for p in self.positions if p.symbol == symbol), ZERO)

    @property
    def total_exposure(self) -> Decimal:
        return sum((p.notional for p in self.positions), ZERO)

    @property
    def open_risk(self) -> Decimal:
        return sum((p.open_risk for p in self.positions), ZERO)

    def bucket_open_risk(self, bucket: str, buckets: Mapping[str, str]) -> Decimal:
        return sum(
            (p.open_risk for p in self.positions if buckets.get(p.symbol, p.symbol) == bucket),
            ZERO,
        )


@dataclass(frozen=True, slots=True)
class MarketState:
    now: datetime
    bot_status: BotStatus
    data_age_s: float
    clock_drift_ms: float
    blackout: bool = False
    cooldowns: Mapping[str, datetime] = field(default_factory=dict)  # symbol -> no entry until
    buckets: Mapping[str, str] = field(default_factory=dict)  # symbol -> correlation bucket


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    passed: bool
    detail: str = ""
    reason: Reason | None = None


@dataclass(frozen=True, slots=True)
class RiskDecision:
    approved: bool
    qty: Decimal  # 0 when rejected
    notional: Decimal
    risk_amount: Decimal  # loss if the stop is hit at the planned price (excl. gap)
    reasons: tuple[Reason, ...]
    checks: tuple[CheckResult, ...]  # full explainability trail (SPEC 1.5)
    adjustments: tuple[str, ...] = ()
    # tick-rounded prices the order manager must use (sizing was computed on these)
    entry: Decimal = ZERO
    stop: Decimal = ZERO
    tp1: Decimal | None = None

    def explain(self) -> str:
        lines = [f"{'OK ' if c.passed else 'FAIL'} {c.name}: {c.detail}" for c in self.checks]
        return "\n".join(lines + [f"adjusted: {a}" for a in self.adjustments])
