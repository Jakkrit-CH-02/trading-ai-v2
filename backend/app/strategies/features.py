"""Feature container + multi-timeframe alignment that cannot look ahead."""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd

from app.exchange.types import INTERVAL_MS


@dataclass(frozen=True)
class Features:
    """Per-bar feature arrays for one symbol on the strategy's execution timeframe.

    ``evaluate(features, i)`` may read index ``<= i`` only. Arrays are numpy so the
    backtest loop stays fast; ``interval`` lets the engine convert bars to time.
    """

    symbol: str
    interval: str
    index: pd.DatetimeIndex
    cols: dict[str, np.ndarray[Any, Any]]

    def __len__(self) -> int:
        return len(self.index)

    def __getitem__(self, key: str) -> np.ndarray[Any, Any]:
        return self.cols[key]

    def time(self, i: int) -> datetime:
        ts: datetime = self.index[i].to_pydatetime()
        return ts

    @staticmethod
    def from_frame(symbol: str, interval: str, df: pd.DataFrame) -> "Features":
        return Features(
            symbol, interval, pd.DatetimeIndex(df.index), {c: df[c].to_numpy() for c in df.columns}
        )


def align_htf(
    htf: pd.DataFrame, htf_interval: str, ltf_index: pd.DatetimeIndex, ltf_interval: str
) -> pd.DataFrame:
    """Higher-timeframe columns as known at each lower-timeframe bar's *close*.

    A 4H bar is usable only once it has closed: it is keyed by its close time and each
    1H bar takes the latest 4H bar whose close time <= that 1H bar's close time. So a
    1H bar inside 08:00-12:00 sees the 4H bar that closed at 08:00, never the one that
    closes at 12:00.
    """
    shifted = htf.copy()
    shifted.index = shifted.index + pd.Timedelta(milliseconds=INTERVAL_MS[htf_interval])
    ltf_close = ltf_index + pd.Timedelta(milliseconds=INTERVAL_MS[ltf_interval])
    out = shifted.reindex(ltf_close, method="ffill")
    out.index = ltf_index
    return out


def dec(x: float, places: int = 8) -> Decimal:
    """float analytic value -> Decimal price (rounded; exchange tick rounding is Phase 3)."""
    return Decimal(repr(round(float(x), places)))
