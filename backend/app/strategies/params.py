"""Strategy parameters. Defaults are the SPEC section 2 values; every one is overridable
(config / walk-forward grid). Frozen so a backtest's parameters cannot change mid-run."""

from dataclasses import dataclass, field
from typing import Any

from app.strategies.types import Regime


@dataclass(frozen=True, slots=True)
class RegimeParams:
    adx_period: int = 14
    adx_trend: float = 25.0
    adx_range: float = 20.0
    ema_fast: int = 50
    ema_slow: int = 200
    slope_lookback: int = 5  # EMA200 slope = ema200[t] - ema200[t - lookback]
    bb_period: int = 20
    stat_window: int = 540  # 90 days of 4h bars for the percentile tests
    vol_quantile: float = 0.90
    atr_period: int = 14


@dataclass(frozen=True, slots=True)
class S1Params:
    ema_fast: int = 20
    ema_slow: int = 50
    rsi_period: int = 14
    rsi_level: float = 50.0
    atr_period: int = 14
    pullback_lookback: int = 6  # bars in which price must have touched EMA20/50
    swing_lookback: int = 10
    stop_atr: float = 0.5
    # SPEC 2.2 says 1.5R, but SPEC 3.5 needs R:R >= 1.5 *after costs*, which 1.5R can never meet
    # (~1.2 after fees). Decision (2026-11-20): TP1 at 2R.
    tp1_r: float = 2.0
    trail_mult: float = 3.0
    trail_period: int = 22
    regimes: tuple[Regime, ...] = (Regime.TREND_UP,)
    regime: RegimeParams = field(default_factory=RegimeParams)


@dataclass(frozen=True, slots=True)
class S2Params:
    bb_period: int = 20
    bb_k: float = 2.0
    rsi_period: int = 14
    rsi_oversold: float = 30.0
    atr_period: int = 14
    stop_atr: float = 1.5
    time_stop_bars: int = 12
    regimes: tuple[Regime, ...] = (Regime.RANGE,)
    regime: RegimeParams = field(default_factory=RegimeParams)


@dataclass(frozen=True, slots=True)
class S3Params:
    bb_period: int = 20
    squeeze_pct: float = 0.20
    stat_window: int = 540
    donchian: int = 20
    vol_mult: float = 1.5
    vol_period: int = 20
    atr_period: int = 14
    trail_mult: float = 2.5
    false_breakout_bars: int = 3
    # SPEC 2.1 enables S3 only in TREND_UP. Squeezes usually happen at low ADX, so this
    # strategy may rarely fire with the default; widen via config, don't assume.
    regimes: tuple[Regime, ...] = (Regime.TREND_UP,)
    regime: RegimeParams = field(default_factory=RegimeParams)


@dataclass(frozen=True, slots=True)
class S4Params:
    lookback: int = 168  # bars (1h) used to find support/resistance
    min_levels: int = 10
    max_levels: int = 20
    min_spacing_fee_mult: float = 3.0  # spacing >= 3x round-trip fee (SPEC 2.2)
    stop_atr: float = 1.0
    atr_period: int = 14
    allocation: float = 0.25  # share of equity committed to one grid
    regimes: tuple[Regime, ...] = (Regime.RANGE,)
    regime: RegimeParams = field(default_factory=RegimeParams)


def with_overrides(params: Any, overrides: dict[str, Any]) -> Any:
    """Return a copy of a frozen params dataclass with some fields replaced."""
    from dataclasses import replace

    return replace(params, **overrides)
