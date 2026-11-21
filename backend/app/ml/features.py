"""ML features (SPEC 4.1), computed from closed candles only.

Every column at bar ``t`` depends on bars ``<= t`` (``tests/test_ml_features.py`` proves it by
truncating the series). Higher-timeframe columns go through ``align_htf`` so a 4h bar is visible
only after it has closed. They are added to the strategy's ``Features`` with an ``ml_`` prefix, so
the backtest and the live runner read exactly the same numbers (SPEC principle 2).

Candle-only on purpose: funding, open interest and order-book imbalance have no history in our
database, so a model trained on them could not be backtested honestly.
"""

import numpy as np
import pandas as pd

from app.marketdata import indicators as ind
from app.strategies import regime as regime_mod
from app.strategies.base import MarketFrames
from app.strategies.features import Features, align_htf
from app.strategies.types import Regime

PREFIX = "ml_"
REGIMES = [r.value for r in Regime]
REGIME_CODE = {r: i for i, r in enumerate(REGIMES)}  # NaN during warm-up
BASE_FEATURES = [
    "ret_1", "ret_3", "ret_6", "ret_12", "ret_24", "rsi14", "adx14", "atr_pct", "bb_width_pct",
    "dist_ema20", "dist_ema50", "dist_ema200", "vol_z", "taker_buy_ratio", "btc_ret_24",
    "hour", "dow", "regime", "btc_regime", "adx_4h",
]  # fmt: skip
SIGNAL_FEATURES = ["s_tech", "risk_pct", "rr"]  # known when the signal fires
FEATURE_NAMES = [*BASE_FEATURES, *SIGNAL_FEATURES]


def feature_frame(data: MarketFrames) -> pd.DataFrame:
    """Candle features on the 1h index (the execution timeframe of S1-S3)."""
    df = data.frames["1h"]
    idx = pd.DatetimeIndex(df.index)
    close, high, low = df["close"], df["high"], df["low"]
    out = pd.DataFrame(index=df.index)
    logc = np.log(close)
    for n in (1, 3, 6, 12, 24):
        out[f"ret_{n}"] = logc.diff(n)
    out["rsi14"] = ind.rsi(close, 14)
    out["adx14"] = ind.adx(high, low, close, 14)[0]
    out["atr_pct"] = ind.atr_pct(high, low, close, 14)
    out["bb_width_pct"] = ind.rolling_percentile(ind.bollinger(close, 20)[3], 500)
    for n in (20, 50, 200):
        out[f"dist_ema{n}"] = close / ind.ema(close, n) - 1
    out["vol_z"] = ind.volume_zscore(df["volume"], 20)
    if "taker_buy_volume" in df.columns:
        out["taker_buy_ratio"] = (
            (df["taker_buy_volume"] / df["volume"].replace(0, np.nan)).rolling(6).mean()
        )
    else:
        out["taker_buy_ratio"] = np.nan
    own = regime_mod.classify(data.frames["4h"])
    own_al = align_htf(own[["regime", "adx"]], "4h", idx, "1h")
    btc4 = data.btc_4h if data.btc_4h is not None else data.frames["4h"]
    btc_reg = regime_mod.classify(btc4)[["regime"]]
    btc_ret = pd.DataFrame({"r": np.log(btc4["close"]).diff(6)})  # 24h = 6 x 4h bars
    out["btc_ret_24"] = align_htf(btc_ret, "4h", idx, "1h")["r"]
    out["regime"] = own_al["regime"].map(REGIME_CODE)
    out["btc_regime"] = align_htf(btc_reg, "4h", idx, "1h")["regime"].map(REGIME_CODE)
    out["adx_4h"] = own_al["adx"]
    out["hour"] = idx.hour
    out["dow"] = idx.day_of_week
    return out[BASE_FEATURES].astype("float64")


def with_ml_features(feats: Features, data: MarketFrames) -> Features:
    """The strategy's features plus the ML columns (``ml_*``), aligned to its index."""
    ff = feature_frame(data).reindex(feats.index)
    cols = dict(feats.cols)
    for c in ff.columns:
        cols[PREFIX + c] = ff[c].to_numpy()
    return Features(feats.symbol, feats.interval, feats.index, cols)


def row_vector(
    feats: Features, i: int, s_tech: float, entry: float, stop: float, tp: float
) -> list[float]:
    """The model input for a signal fired at the close of bar ``i`` (order = FEATURE_NAMES)."""
    base = [float(feats.cols[PREFIX + n][i]) for n in BASE_FEATURES]
    risk = (entry - stop) / entry if entry else float("nan")
    rr = (tp - entry) / (entry - stop) if entry > stop else float("nan")
    return [*base, s_tech, risk, rr]
