"""Deterministic synthetic markets for strategy tests (not for judging profitability)."""

import numpy as np
import pandas as pd

from app.strategies.base import MarketFrames

START = pd.Timestamp("2022-01-01", tz="UTC")


def make_1h(
    segments: list[tuple[str, int]], seed: int = 1, start_price: float = 100.0
) -> pd.DataFrame:
    """Build 1h OHLCV from a list of ``(kind, hours)`` segments.

    kinds: up, down, range, squeeze (low-vol drift then a volume-backed breakout burst).
    """
    rng = np.random.default_rng(seed)
    closes: list[float] = []
    vols: list[float] = []
    price = start_price
    level = start_price
    for kind, hours in segments:
        level = price
        for h in range(hours):
            vol = 1000.0 * (1 + 0.3 * rng.standard_normal())
            if kind == "up":
                price *= 1 + 0.0006 + 0.004 * rng.standard_normal()
            elif kind == "down":
                price *= 1 - 0.0006 + 0.004 * rng.standard_normal()
            elif kind == "range":
                price += 0.12 * (level - price) + level * 0.006 * rng.standard_normal()
            elif kind == "squeeze":
                if h < hours - 30:
                    price *= 1 + 0.0004 * rng.standard_normal()
                    vol *= 0.6
                else:  # breakout burst
                    price *= 1 + 0.006 + 0.002 * rng.standard_normal()
                    vol *= 3.0
            else:
                raise ValueError(kind)
            closes.append(max(price, 1.0))
            vols.append(max(vol, 1.0))
    c = np.array(closes)
    o = np.concatenate([[start_price], c[:-1]])
    wick = np.abs(rng.standard_normal(len(c))) * 0.0015
    hi = np.maximum(o, c) * (1 + wick)
    lo = np.minimum(o, c) * (1 - np.abs(rng.standard_normal(len(c))) * 0.0015)
    idx = pd.date_range(START, periods=len(c), freq="1h")
    df = pd.DataFrame({"open": o, "high": hi, "low": lo, "close": c, "volume": vols}, index=idx)
    df["quote_volume"] = df["volume"] * df["close"]
    return df


def to_4h(df1: pd.DataFrame) -> pd.DataFrame:
    g = df1.resample("4h", closed="left", label="left")
    out = pd.DataFrame(
        {
            "open": g["open"].first(),
            "high": g["high"].max(),
            "low": g["low"].min(),
            "close": g["close"].last(),
            "volume": g["volume"].sum(),
            "quote_volume": g["quote_volume"].sum(),
            "n": g["close"].count(),
        }
    )
    return out[out["n"] == 4].drop(columns="n")  # complete (closed) 4h bars only


def frames(df1: pd.DataFrame, symbol: str = "BTCUSDT") -> MarketFrames:
    return MarketFrames(symbol, {"1h": df1, "4h": to_4h(df1)})


def truncate(df1: pd.DataFrame, n_bars: int, symbol: str = "BTCUSDT") -> MarketFrames:
    """Frames as they would look after only the first ``n_bars`` 1h bars have closed."""
    return frames(df1.iloc[:n_bars], symbol)


def standard_market() -> pd.DataFrame:
    segs = [("up", 1500), ("range", 1200), ("squeeze", 400), ("up", 800), ("down", 900),
            ("range", 1000), ("up", 1200)]  # fmt: skip
    return make_1h(segs, seed=3)
