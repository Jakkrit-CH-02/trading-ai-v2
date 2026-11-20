"""Regime detector (SPEC 2.1). Run on 4H bars; every column is causal.

Precedence when several conditions hold: HIGH_VOL, TREND_UP, TREND_DOWN, RANGE.
Anything else (including the warm-up period) is NEUTRAL, which enables no strategy.
HIGH_VOL also enables nothing here: SPEC allows "no new orders *or* half size"; the
conservative choice is blocking. The AI-news flag for HIGH_VOL arrives in Phase 6.
"""

import numpy as np
import pandas as pd

from app.marketdata import indicators as ind
from app.strategies.params import RegimeParams
from app.strategies.types import Regime


def classify(df4h: pd.DataFrame, p: RegimeParams | None = None) -> pd.DataFrame:
    """Return a frame (same index) with indicator columns and a ``regime`` column."""
    p = p or RegimeParams()
    high, low, close = df4h["high"], df4h["low"], df4h["close"]

    adx, _, _ = ind.adx(high, low, close, p.adx_period)
    ema_f, ema_s = ind.ema(close, p.ema_fast), ind.ema(close, p.ema_slow)
    slope = ema_s - ema_s.shift(p.slope_lookback)
    bbw = ind.bollinger(close, p.bb_period)[3]
    bbw_median = bbw.rolling(p.stat_window, min_periods=p.stat_window).median()
    atrp = ind.atr_pct(high, low, close, p.atr_period)
    atrp_hi = atrp.rolling(p.stat_window, min_periods=p.stat_window).quantile(p.vol_quantile)

    high_vol = atrp > atrp_hi
    up = (adx > p.adx_trend) & (ema_f > ema_s) & (slope > 0)
    down = (adx > p.adx_trend) & (ema_f < ema_s)
    rng = (adx < p.adx_range) & (bbw < bbw_median)
    regime = np.select(
        [high_vol, up, down, rng],
        [Regime.HIGH_VOL, Regime.TREND_UP, Regime.TREND_DOWN, Regime.RANGE],
        default=Regime.NEUTRAL,
    )
    return pd.DataFrame(
        {
            "adx": adx,
            "ema_fast": ema_f,
            "ema_slow": ema_s,
            "ema_slow_slope": slope,
            "bb_width": bbw,
            "atr_pct": atrp,
            "regime": pd.Series(regime, index=df4h.index, dtype="object"),
        },
        index=df4h.index,
    )
