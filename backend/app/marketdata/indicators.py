"""Technical indicators on pandas Series.

Design rules
- **Causal only**: the value at bar ``t`` depends on bars ``<= t``. Nothing here may peek
  forward, so backtest and live agree (SPEC section 2.4). ``tests/test_indicators.py``
  proves this by truncating the series.
- Smoothing follows Wilder / TA-Lib conventions: EMA and Wilder averages are seeded with
  the simple mean of the first ``n`` values.
- Indicators are analytics, not money, so they run on ``float``. Prices are converted at the
  boundary (``klines_to_frame``); order sizing converts back to ``Decimal``.
"""

from collections.abc import Sequence

import numpy as np
import pandas as pd

from app.exchange.types import Kline

OHLCV = ["open", "high", "low", "close", "volume"]


def klines_to_frame(klines: Sequence[Kline]) -> pd.DataFrame:
    """Closed klines -> DataFrame indexed by UTC open_time (ascending)."""
    df = pd.DataFrame(
        {
            "open": [float(k.o) for k in klines],
            "high": [float(k.h) for k in klines],
            "low": [float(k.l) for k in klines],
            "close": [float(k.c) for k in klines],
            "volume": [float(k.v) for k in klines],
            "taker_buy_volume": [float(k.taker_buy_v) for k in klines],
        },
        index=pd.DatetimeIndex([k.open_time for k in klines], name="open_time", tz="UTC"),
    )
    return df.sort_index()


def _seeded_smooth(s: pd.Series, n: int, alpha: float) -> pd.Series:
    """Exponential smoothing seeded with the SMA of the first ``n`` valid values."""
    out = pd.Series(np.nan, index=s.index, dtype="float64")
    valid = s.dropna()
    if len(valid) < n:
        return out
    seed_pos = s.index.get_loc(valid.index[n - 1])
    assert isinstance(seed_pos, int)
    seeded = s.copy()
    seeded.iloc[:seed_pos] = np.nan
    seeded.iloc[seed_pos] = valid.iloc[:n].mean()
    return (
        seeded.ewm(alpha=alpha, adjust=False)
        .mean()
        .where(np.arange(len(s)) >= seed_pos, other=np.nan)
    )


def sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()


def ema(s: pd.Series, n: int) -> pd.Series:
    return _seeded_smooth(s, n, alpha=2.0 / (n + 1))


def wilder(s: pd.Series, n: int) -> pd.Series:
    return _seeded_smooth(s, n, alpha=1.0 / n)


def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI. Flat series (no gains, no losses) -> 50."""
    delta = close.diff()
    avg_gain = wilder(delta.clip(lower=0.0), n)
    avg_loss = wilder((-delta).clip(lower=0.0), n)
    rs = avg_gain / avg_loss
    out = 100.0 - 100.0 / (1.0 + rs)
    out = out.where(avg_loss != 0, 100.0)  # only gains -> 100
    return out.where(~((avg_gain == 0) & (avg_loss == 0)), 50.0).where(avg_gain.notna())


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([high - low, (high - prev_close).abs(), (low - prev_close).abs()], axis=1).max(
        axis=1
    )
    tr.iloc[0] = high.iloc[0] - low.iloc[0]
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return wilder(true_range(high, low, close), n)


def atr_pct(high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14) -> pd.Series:
    return atr(high, low, close, n) / close


def adx(
    high: pd.Series, low: pd.Series, close: pd.Series, n: int = 14
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return ``(adx, plus_di, minus_di)`` using Wilder smoothing."""
    up = high.diff()
    down = -low.diff()
    plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=high.index)
    minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=high.index)
    plus_dm.iloc[0] = minus_dm.iloc[0] = np.nan
    tr = true_range(high, low, close)
    tr.iloc[0] = np.nan
    sm_tr = wilder(tr, n)
    plus_di = 100.0 * wilder(plus_dm, n) / sm_tr
    minus_di = 100.0 * wilder(minus_dm, n) / sm_tr
    denom = (plus_di + minus_di).replace(0.0, np.nan)
    dx = 100.0 * (plus_di - minus_di).abs() / denom
    return wilder(dx, n), plus_di, minus_di


def bollinger(
    close: pd.Series, n: int = 20, k: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series, pd.Series]:
    """Return ``(mid, upper, lower, width)``; width = (upper - lower) / mid. Population std."""
    mid = sma(close, n)
    std = close.rolling(n, min_periods=n).std(ddof=0)
    upper, lower = mid + k * std, mid - k * std
    return mid, upper, lower, (upper - lower) / mid


def rolling_percentile(s: pd.Series, window: int) -> pd.Series:
    """Share (0..1) of the last ``window`` values (incl. current) that are <= current."""
    return s.rolling(window, min_periods=window).apply(
        lambda w: float((w <= w[-1]).mean()), raw=True
    )


def donchian(high: pd.Series, low: pd.Series, n: int = 20) -> tuple[pd.Series, pd.Series]:
    """Highest high / lowest low over the ``n`` bars ending at ``t`` inclusive.

    For breakout rules compare ``close[t]`` with ``upper.shift(1)[t]`` so the current bar
    does not define its own channel.
    """
    return high.rolling(n, min_periods=n).max(), low.rolling(n, min_periods=n).min()


def volume_zscore(volume: pd.Series, n: int = 20) -> pd.Series:
    mean = volume.rolling(n, min_periods=n).mean()
    std = volume.rolling(n, min_periods=n).std(ddof=0).replace(0.0, np.nan)
    return (volume - mean) / std
