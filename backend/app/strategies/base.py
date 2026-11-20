"""Strategy contract. A strategy is two pure functions:

- ``prepare(data)``: vectorised, causal features for every bar (indicators + aligned
  higher-timeframe regime). Computed once per backtest, or incrementally in live.
- ``evaluate(features, i)``: decide at the close of bar ``i`` using only ``features[:i+1]``.

Nothing here talks to an exchange, a clock or a database, so backtest, paper and live run
the exact same code (SPEC principle 2). ``tests/test_strategies.py`` proves no look-ahead.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Protocol

import numpy as np
import pandas as pd

from app.exchange.types import INTERVAL_MS
from app.strategies import regime as regime_mod
from app.strategies.features import Features, align_htf
from app.strategies.params import RegimeParams
from app.strategies.types import Signal


@dataclass(frozen=True)
class MarketFrames:
    """Closed-candle OHLCV frames for one symbol, keyed by interval ('1h', '4h', ...)."""

    symbol: str
    frames: dict[str, pd.DataFrame]
    btc_4h: pd.DataFrame | None = field(default=None)  # market filter source (SPEC 2.1)


class Strategy(Protocol):
    name: str
    exec_interval: str

    def prepare(self, data: MarketFrames) -> Features: ...

    def evaluate(self, f: Features, i: int) -> Signal | None: ...


def base_columns(df: pd.DataFrame, interval: str) -> dict[str, pd.Series]:
    bars_24h = max(1, 86_400_000 // INTERVAL_MS[interval])
    return {
        "open": df["open"],
        "high": df["high"],
        "low": df["low"],
        "close": df["close"],
        "volume": df["volume"],
        "qv24h": df["quote_volume"].rolling(bars_24h, min_periods=bars_24h).sum(),
    }


def regime_columns(
    data: MarketFrames, ltf_index: pd.Index, ltf_interval: str, p: RegimeParams
) -> dict[str, pd.Series]:
    """4H regime of the symbol and of BTC, aligned causally to the execution timeframe."""
    ltf_index = pd.DatetimeIndex(ltf_index)
    own = regime_mod.classify(data.frames["4h"], p)
    own_al = align_htf(own[["regime", "adx"]], "4h", ltf_index, ltf_interval)
    if data.btc_4h is not None:
        btc = regime_mod.classify(data.btc_4h, p)
        btc_al = align_htf(btc[["regime"]], "4h", ltf_index, ltf_interval)["regime"]
    else:
        btc_al = own_al["regime"]  # the symbol *is* BTC (or no market filter available)
    return {"regime4": own_al["regime"], "adx4": own_al["adx"], "btc_regime": btc_al}


def to_features(symbol: str, interval: str, cols: dict[str, pd.Series]) -> Features:
    df = pd.DataFrame(cols)
    return Features.from_frame(symbol, interval, df)


def s_tech_score(factors: Sequence[bool], base: float = 60.0) -> float:
    """S_tech (SPEC 2.3): all entry rules already hold (base 60) plus 10 per confirming
    factor (multi-timeframe alignment, trend strength, volume...). Range 60..100 for four
    factors. With S_ml = S_ai = 50, a total score >= 60 needs S_tech >= ~72 (>= 2 factors).
    """
    return base + 10.0 * sum(bool(x) for x in factors)


def is_nan(*values: float) -> bool:
    return any(bool(np.isnan(v)) for v in values)
