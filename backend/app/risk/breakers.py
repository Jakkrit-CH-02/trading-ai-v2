"""Circuit breakers and the kill switch (SPEC 3.3).

Time is always passed in (``now``), never read from a clock, so behaviour is deterministic.
Rules of thumb encoded here:
- Breakers block **new entries**. Existing positions keep being managed (their stops live on
  the exchange).
- Max drawdown trips the **kill switch**, which is latched: it only clears through
  ``reset_kill`` with a verified second factor.
- A 418 (IP ban) latches too, until its ban window passes.
- Exchange-side incidents (hack, withdrawal halt, stablecoin depeg) pause entries and ask a
  human; they never auto-close positions.
"""

import enum
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

from app.risk.profile import RiskProfile
from app.risk.types import ZERO, PortfolioState


class BreakerKind(enum.StrEnum):
    KILL_SWITCH = "KILL_SWITCH"
    DAILY_LOSS = "DAILY_LOSS"
    WEEKLY_LOSS = "WEEKLY_LOSS"
    VOLATILITY = "VOLATILITY"
    STALE_DATA = "STALE_DATA"
    API_ERRORS = "API_ERRORS"
    RATE_LIMIT = "RATE_LIMIT"
    IP_BAN = "IP_BAN"
    EXCHANGE_EVENT = "EXCHANGE_EVENT"


@dataclass(frozen=True, slots=True)
class ActiveBreaker:
    kind: BreakerKind
    detail: str
    until: datetime | None  # None = until a human clears it
    latched: bool = False


class KillSwitchError(RuntimeError):
    pass


def _next_utc_midnight(now: datetime) -> datetime:
    return (now + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)


@dataclass(slots=True)
class CircuitBreakers:
    profile: RiskProfile
    _timed: dict[BreakerKind, ActiveBreaker] = field(default_factory=dict)
    _kill: ActiveBreaker | None = None
    _exchange_event: ActiveBreaker | None = None
    _ban: ActiveBreaker | None = None
    _loss_streak: int = 0
    _halved: bool = False
    _wins_since_halved: int = 0
    _api_errors: deque[datetime] = field(default_factory=deque)
    _slippage: deque[Decimal] = field(default_factory=deque)
    _last_tick: datetime | None = None

    # ---- inputs -------------------------------------------------------------------------

    def observe_equity(self, now: datetime, p: PortfolioState) -> None:
        """Evaluate loss limits. Call before every decision (the engine does)."""
        if (
            p.peak_equity > 0
            and (p.peak_equity - p.equity) / p.peak_equity >= self.profile.max_drawdown
        ):
            self.trigger_kill(
                now, f"drawdown {(p.peak_equity - p.equity) / p.peak_equity:.1%} from peak"
            )
        if p.day_start_equity > 0:
            day = (p.equity - p.day_start_equity) / p.day_start_equity
            if day <= -self.profile.daily_loss:
                self._pause(
                    BreakerKind.DAILY_LOSS, f"daily loss {day:.1%}", _next_utc_midnight(now)
                )
        if p.week_start_equity > 0:
            week = (p.equity - p.week_start_equity) / p.week_start_equity
            if week <= -self.profile.weekly_loss:
                self._pause(
                    BreakerKind.WEEKLY_LOSS, f"weekly loss {week:.1%}", now + timedelta(days=7)
                )

    def record_trade_result(self, pnl: Decimal, slippage: Decimal | None = None) -> None:
        if pnl < 0:
            self._loss_streak += 1
            self._wins_since_halved = 0
            if self._loss_streak >= self.profile.loss_streak:
                self._halved = True
        elif pnl > 0:
            self._loss_streak = 0
            if self._halved:
                self._wins_since_halved += 1
                if self._wins_since_halved >= self.profile.streak_recovery_wins:
                    self._halved = False
                    self._wins_since_halved = 0
        if slippage is not None:
            self._slippage.append(slippage)
            while len(self._slippage) > self.profile.slippage_window:
                self._slippage.popleft()

    def record_api_error(
        self, now: datetime, status: int | None = None, retry_after: float = 60.0
    ) -> None:
        """429 pauses for ``retry_after``; 418 stops immediately; others count toward a limit."""
        if status == 418:
            until = now + timedelta(seconds=max(retry_after, 1.0))
            self._ban = ActiveBreaker(
                BreakerKind.IP_BAN, "HTTP 418: IP banned", until, latched=True
            )
            return
        if status == 429:
            until = now + timedelta(seconds=max(retry_after, 1.0))
            self._pause(BreakerKind.RATE_LIMIT, "HTTP 429: rate limited", until)
            return
        self._api_errors.append(now)
        window = timedelta(seconds=self.profile.api_error_window_s)
        while self._api_errors and now - self._api_errors[0] > window:
            self._api_errors.popleft()
        if len(self._api_errors) >= self.profile.api_error_limit:
            until = now + timedelta(seconds=self.profile.api_error_pause_s)
            self._pause(
                BreakerKind.API_ERRORS,
                f"{len(self._api_errors)} API errors in {window.seconds}s",
                until,
            )

    def record_tick(self, now: datetime) -> None:
        self._last_tick = now

    def observe_market(self, now: datetime, one_min_move: Decimal, atr_to_median: Decimal) -> None:
        """1m candle move > 3% or ATR > 3x its 30-day median => pause 60 minutes."""
        if (
            abs(one_min_move) > self.profile.vol_spike_move
            or atr_to_median > self.profile.vol_spike_atr_ratio
        ):
            until = now + timedelta(minutes=self.profile.vol_pause_minutes)
            self._pause(
                BreakerKind.VOLATILITY,
                f"1m move {one_min_move:.2%}, ATR {atr_to_median:.1f}x median",
                until,
            )

    def flag_exchange_event(self, reason: str) -> None:
        self._exchange_event = ActiveBreaker(BreakerKind.EXCHANGE_EVENT, reason, None, latched=True)

    def clear_exchange_event(self) -> None:
        self._exchange_event = None

    # ---- kill switch --------------------------------------------------------------------

    def trigger_kill(self, now: datetime, reason: str) -> None:
        if self._kill is None:  # keep the first reason
            self._kill = ActiveBreaker(BreakerKind.KILL_SWITCH, reason, None, latched=True)

    def reset_kill(self, totp_verified: bool) -> None:
        if not totp_verified:
            raise KillSwitchError("kill switch reset requires a verified second factor")
        self._kill = None

    # ---- queries ------------------------------------------------------------------------

    def _pause(self, kind: BreakerKind, detail: str, until: datetime) -> None:
        cur = self._timed.get(kind)
        if cur is None or cur.until is None or until > cur.until:
            self._timed[kind] = ActiveBreaker(kind, detail, until)

    @property
    def kill_switch_active(self) -> bool:
        return self._kill is not None

    def active(self, now: datetime) -> list[ActiveBreaker]:
        out: list[ActiveBreaker] = []
        if self._kill is not None:
            out.append(self._kill)
        if self._ban is not None:
            if self._ban.until is not None and now >= self._ban.until:
                self._ban = None  # window passed; the next request decides whether we are free
            else:
                out.append(self._ban)
        if self._exchange_event is not None:
            out.append(self._exchange_event)
        for kind, b in list(self._timed.items()):
            if b.until is not None and now >= b.until:
                del self._timed[kind]
            else:
                out.append(b)
        if self._last_tick is None:  # fail safe: never traded on data we have not seen
            out.append(ActiveBreaker(BreakerKind.STALE_DATA, "no tick received yet", None))
        else:
            age = (now - self._last_tick).total_seconds()
            if age > self.profile.stale_tick_s:
                out.append(ActiveBreaker(BreakerKind.STALE_DATA, f"no tick for {age:.0f}s", None))
        return out

    def entries_blocked(self, now: datetime) -> bool:
        return bool(self.active(now))

    @property
    def risk_multiplier(self) -> Decimal:
        """0.5 after a losing streak, back to 1 after the required wins."""
        return Decimal("0.5") if self._halved else Decimal(1)

    @property
    def force_limit_orders(self) -> bool:
        """Average slippage over the last N trades above the limit => no more market orders."""
        if len(self._slippage) < self.profile.slippage_min_samples:
            return False
        avg = sum(self._slippage, ZERO) / len(self._slippage)
        return avg > self.profile.slippage_avg_limit
