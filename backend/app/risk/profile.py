"""Risk profile. Defaults are SPEC section 3; hard bounds stop a bad config from loosening
the system past the SPEC maximums (e.g. risk per trade can never exceed 1%)."""

from dataclasses import dataclass
from decimal import Decimal


class RiskConfigError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RiskProfile:
    # position sizing (3.1)
    risk_per_trade: Decimal = Decimal("0.005")
    risk_per_trade_cap: Decimal = Decimal("0.01")  # SPEC: max allowed in config
    kelly_cap_fraction: Decimal = Decimal("0.25")  # risk <= 1/4 Kelly when Kelly inputs exist
    fee_rate: Decimal = Decimal("0.001")  # taker, per fill
    slippage_rate: Decimal = Decimal("0.0005")  # assumed per side
    # exposure (3.2)
    max_positions: int = 4
    max_symbol_exposure: Decimal = Decimal("0.25")
    max_total_exposure: Decimal = Decimal("0.80")  # Spot
    max_open_risk: Decimal = Decimal("0.02")
    max_bucket_risk: Decimal = Decimal("0.0125")
    min_cash_reserve: Decimal = Decimal("0.20")
    # circuit breakers (3.3)
    daily_loss: Decimal = Decimal("0.02")
    weekly_loss: Decimal = Decimal("0.05")
    max_drawdown: Decimal = Decimal("0.12")
    loss_streak: int = 4
    streak_recovery_wins: int = 2
    vol_spike_move: Decimal = Decimal("0.03")  # 1m candle move
    vol_spike_atr_ratio: Decimal = Decimal("3")
    vol_pause_minutes: int = 60
    stale_tick_s: float = 10.0
    api_error_limit: int = 5
    api_error_window_s: int = 60
    api_error_pause_s: int = 60
    slippage_avg_limit: Decimal = Decimal("0.0015")
    slippage_window: int = 20
    slippage_min_samples: int = 10
    # pre-trade checklist (3.5)
    min_rr: Decimal = Decimal("1.5")
    max_data_age_s: float = 5.0
    max_clock_drift_ms: float = 500.0
    max_slippage_bps: Decimal = Decimal("30")  # market orders (project rule)

    def __post_init__(self) -> None:
        def need(ok: bool, msg: str) -> None:
            if not ok:
                raise RiskConfigError(msg)

        need(
            Decimal(0) < self.risk_per_trade <= self.risk_per_trade_cap,
            "risk_per_trade must be in (0, cap]",
        )
        need(
            self.risk_per_trade_cap <= Decimal("0.01"),
            "risk_per_trade_cap may not exceed 1% (SPEC 3.1)",
        )
        need(
            Decimal(0) < self.kelly_cap_fraction <= Decimal("0.25"),
            "kelly_cap_fraction must be in (0, 0.25]",
        )
        need(
            Decimal(0) <= self.fee_rate < Decimal("0.01")
            and Decimal(0) <= self.slippage_rate < Decimal("0.05"),
            "implausible costs",
        )
        need(self.max_positions >= 1, "max_positions >= 1")
        for name in ("max_symbol_exposure", "max_total_exposure", "min_cash_reserve"):
            v = getattr(self, name)
            need(Decimal(0) < v <= Decimal(1), f"{name} must be in (0, 1]")
        need(
            self.max_total_exposure + self.min_cash_reserve <= Decimal(1),
            "total exposure + cash reserve > 100%",
        )
        need(
            self.max_symbol_exposure <= self.max_total_exposure, "symbol exposure > total exposure"
        )
        need(
            Decimal(0) < self.max_bucket_risk <= self.max_open_risk,
            "bucket risk must be in (0, open risk]",
        )
        need(
            Decimal(0) < self.daily_loss <= self.weekly_loss <= self.max_drawdown < Decimal(1),
            "loss limits must nest: daily <= weekly <= max drawdown",
        )
        need(self.min_rr >= Decimal(1), "min_rr must be >= 1")
        need(
            self.loss_streak >= 1 and self.streak_recovery_wins >= 1, "streak settings must be >= 1"
        )
