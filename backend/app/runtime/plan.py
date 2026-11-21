"""A signal's exit rules, stored with the signal so a restart can keep managing the position
exactly as the strategy specified (trailing stop, time stop, false-breakout exit)."""

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from app.strategies.types import Signal, TrailSpec


@dataclass(frozen=True, slots=True)
class ExitPlan:
    tp1_close_fraction: Decimal = Decimal("0.5")
    trail: TrailSpec | None = None
    time_stop_bars: int | None = None
    false_breakout: tuple[Decimal, int] | None = None  # (level, within_bars)

    def to_json(self) -> dict[str, Any]:
        return {
            "tp1_close_fraction": str(self.tp1_close_fraction),
            "trail": None
            if self.trail is None
            else {
                "mult": self.trail.mult,
                "period": self.trail.period,
                "after_tp1": self.trail.after_tp1,
            },
            "time_stop_bars": self.time_stop_bars,
            "false_breakout": None
            if self.false_breakout is None
            else [str(self.false_breakout[0]), self.false_breakout[1]],
        }

    @staticmethod
    def from_json(d: dict[str, Any] | None) -> "ExitPlan":
        if not d:
            return ExitPlan()
        t, fb = d.get("trail"), d.get("false_breakout")
        return ExitPlan(
            tp1_close_fraction=Decimal(d.get("tp1_close_fraction", "0.5")),
            trail=None if not t else TrailSpec(t["mult"], t["period"], t["after_tp1"]),
            time_stop_bars=d.get("time_stop_bars"),
            false_breakout=None if not fb else (Decimal(fb[0]), int(fb[1])),
        )

    @staticmethod
    def of(sig: Signal) -> "ExitPlan":
        return ExitPlan(sig.tp1_close_fraction, sig.trail, sig.time_stop_bars, sig.false_breakout)


def jsonable(value: Any) -> Any:
    """``Signal.reasons`` holds numpy floats / Decimals / enums: make them JSON-safe."""
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [jsonable(v) for v in value]
    if isinstance(value, bool | int | str) or value is None:
        return value
    if isinstance(value, float):
        return value if value == value else None  # NaN is not valid JSON
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f if f == f else None
