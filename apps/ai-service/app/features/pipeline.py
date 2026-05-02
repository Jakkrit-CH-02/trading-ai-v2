"""Deterministic feature transforms.

Pure functions over an OHLCV pandas DataFrame. No I/O, no global state.
Money columns arrive as strings (transport convention) and are converted
to floats *only* for indicator math — outputs are float64 numerics.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

OHLCV_COLS = ("open", "high", "low", "close", "volume")


def _ensure_float(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in OHLCV_COLS:
        out[col] = out[col].astype(float)
    return out


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False, min_periods=period).mean()


def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


def macd(
    close: pd.Series,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    line = ema(close, fast) - ema(close, slow)
    sig = line.ewm(span=signal, adjust=False, min_periods=signal).mean()
    return line, sig, line - sig


def atr(
    high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14
) -> pd.Series:
    pc = close.shift(1)
    tr = pd.concat(
        [(high - low), (high - pc).abs(), (low - pc).abs()], axis=1
    ).max(axis=1)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def bollinger(
    close: pd.Series, period: int = 20, k: float = 2.0
) -> tuple[pd.Series, pd.Series, pd.Series]:
    mid = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)
    upper = mid + k * std
    lower = mid - k * std
    width = (upper - lower) / mid
    return upper, lower, width


def returns(close: pd.Series, period: int = 1) -> pd.Series:
    return close.pct_change(period)


def volatility(close: pd.Series, period: int = 20) -> pd.Series:
    return returns(close, 1).rolling(period).std(ddof=0)


def volume_zscore(volume: pd.Series, period: int = 20) -> pd.Series:
    mean = volume.rolling(period).mean()
    std = volume.rolling(period).std(ddof=0)
    return (volume - mean) / std.replace(0.0, np.nan)


def compute_features(
    df: pd.DataFrame,
    names: list[str] | None = None,
    *,
    dropna: bool = True,
) -> pd.DataFrame:
    """Apply registered feature functions in deterministic order.

    Returns a DataFrame with `open_time` plus one column per feature, in the
    exact order given by `names` (or DEFAULT_FEATURES if None). When
    `dropna=True` the warm-up rows containing NaNs from rolling/EWM windows
    are removed.
    """
    from .registry import DEFAULT_FEATURES, REGISTRY

    selected = list(names) if names is not None else list(DEFAULT_FEATURES)
    unknown = [n for n in selected if n not in REGISTRY]
    if unknown:
        raise ValueError(f"unknown features: {unknown}")

    work = _ensure_float(df)
    out = pd.DataFrame({"open_time": df["open_time"].astype("int64").to_numpy()})
    for name in selected:
        out[name] = REGISTRY[name](work).astype("float64").to_numpy()

    if dropna:
        out = out.dropna().reset_index(drop=True)
    return out
