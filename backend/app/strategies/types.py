"""Shared strategy types. Strategies return a ``Signal``; they never place orders (SPEC 1.2)."""

import enum
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from app.core.models import Side


class Regime(enum.StrEnum):
    TREND_UP = "TREND_UP"
    TREND_DOWN = "TREND_DOWN"
    RANGE = "RANGE"
    HIGH_VOL = "HIGH_VOL"
    NEUTRAL = "NEUTRAL"  # warm-up, or none of the SPEC 2.1 conditions hold


@dataclass(frozen=True, slots=True)
class TrailSpec:
    """Chandelier-style trailing stop: highest high since entry minus ``mult`` x ATR(period)."""

    mult: float
    period: int
    after_tp1: bool  # S1 trails only the runner after TP1; S3 trails from entry


@dataclass(frozen=True, slots=True)
class Signal:
    strategy: str
    symbol: str
    side: Side
    bar_time: datetime  # open_time of the *closed* bar that produced the signal
    entry: Decimal  # reference price: close of the signal bar
    stop: Decimal
    s_tech: float  # 0..100, see scoring.py
    tp1: Decimal | None = None
    # Reference target used ONLY for the Risk Engine's R:R check; it triggers no exit. For
    # trailing-only strategies (S3) whose exit is the trail, not a limit order.
    rr_target: Decimal | None = None
    tp1_close_fraction: Decimal = Decimal("0.5")  # 1 => tp1 is the full target (S2)
    trail: TrailSpec | None = None
    time_stop_bars: int | None = None
    false_breakout: tuple[Decimal, int] | None = None  # (level, within_bars)
    reasons: dict[str, Any] = field(default_factory=dict)  # explainability (SPEC 1.5)
