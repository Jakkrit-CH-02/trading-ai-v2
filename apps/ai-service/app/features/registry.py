"""Feature name → callable registry.

Insertion order is the canonical feature order. Training and inference
must read this registry to keep their schema aligned.
"""
from __future__ import annotations

from collections import OrderedDict
from typing import Callable

import pandas as pd

from . import pipeline as p

FeatureFn = Callable[[pd.DataFrame], pd.Series]


def _ret_1(df: pd.DataFrame) -> pd.Series:
    return p.returns(df["close"], 1)


def _ret_5(df: pd.DataFrame) -> pd.Series:
    return p.returns(df["close"], 5)


def _ema_12(df: pd.DataFrame) -> pd.Series:
    return p.ema(df["close"], 12)


def _ema_26(df: pd.DataFrame) -> pd.Series:
    return p.ema(df["close"], 26)


def _rsi_14(df: pd.DataFrame) -> pd.Series:
    return p.rsi(df["close"], 14)


def _macd(df: pd.DataFrame) -> pd.Series:
    return p.macd(df["close"])[0]


def _macd_signal(df: pd.DataFrame) -> pd.Series:
    return p.macd(df["close"])[1]


def _macd_hist(df: pd.DataFrame) -> pd.Series:
    return p.macd(df["close"])[2]


def _atr_14(df: pd.DataFrame) -> pd.Series:
    return p.atr(df["high"], df["low"], df["close"], 14)


def _bb_upper(df: pd.DataFrame) -> pd.Series:
    return p.bollinger(df["close"])[0]


def _bb_lower(df: pd.DataFrame) -> pd.Series:
    return p.bollinger(df["close"])[1]


def _bb_width(df: pd.DataFrame) -> pd.Series:
    return p.bollinger(df["close"])[2]


def _vol_20(df: pd.DataFrame) -> pd.Series:
    return p.volatility(df["close"], 20)


def _vz_20(df: pd.DataFrame) -> pd.Series:
    return p.volume_zscore(df["volume"], 20)


REGISTRY: "OrderedDict[str, FeatureFn]" = OrderedDict(
    [
        ("return_1", _ret_1),
        ("return_5", _ret_5),
        ("ema_12", _ema_12),
        ("ema_26", _ema_26),
        ("rsi_14", _rsi_14),
        ("macd", _macd),
        ("macd_signal", _macd_signal),
        ("macd_hist", _macd_hist),
        ("atr_14", _atr_14),
        ("bb_upper", _bb_upper),
        ("bb_lower", _bb_lower),
        ("bb_width", _bb_width),
        ("volatility_20", _vol_20),
        ("volume_zscore_20", _vz_20),
    ]
)

DEFAULT_FEATURES: tuple[str, ...] = tuple(REGISTRY.keys())
