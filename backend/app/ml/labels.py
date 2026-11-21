"""Triple-barrier labels (SPEC 4.1): "does this signal reach its first target before its stop,
within N bars?". The model never predicts price, only this yes/no on the strategy's own signal.

Conventions (deliberately pessimistic, like the backtest):
- the position is entered at the OPEN of the bar after the signal;
- if a bar touches both the stop and the target, the stop counts first;
- if the open already gaps through the stop the label is 0;
- reaching neither barrier within the horizon counts as 0 (no profit target hit).
"""

from collections.abc import Callable
from dataclasses import dataclass

import pandas as pd

from app.ml.features import FEATURE_NAMES, row_vector
from app.strategies.features import Features
from app.strategies.types import Signal

DEFAULT_HORIZON = 48  # bars, when the signal has no time stop


@dataclass(frozen=True, slots=True)
class Label:
    y: int
    end_idx: int  # last bar index the outcome depended on (for purging overlapping samples)


def target_of(sig: Signal) -> float | None:
    t = sig.tp1 if sig.tp1 is not None else sig.rr_target
    return None if t is None else float(t)


def label_signal(feats: Features, i: int, sig: Signal, horizon: int | None = None) -> Label | None:
    """``None`` when the outcome is not known yet (not enough bars after ``i``)."""
    n = len(feats)
    h = horizon or sig.time_stop_bars or DEFAULT_HORIZON
    target = target_of(sig)
    if target is None or i + 1 >= n:
        return None
    stop = float(sig.stop)
    open_, high, low = feats["open"], feats["high"], feats["low"]
    if open_[i + 1] <= stop:
        return Label(0, i + 1)
    last = min(n - 1, i + h)
    for j in range(i + 1, last + 1):
        if low[j] <= stop:
            return Label(0, j)
        if high[j] >= target:
            return Label(1, j)
    return Label(0, last) if i + h <= n - 1 else None  # unresolved at the end of the data


def build_dataset(
    strategy_eval: Callable[[Features, int], Signal | None],
    feats: Features,
    symbol: str,
    horizon: int | None = None,
) -> pd.DataFrame:
    """One row per signal the strategy fires (taken OR skipped - the model must judge them all)."""
    rows = []
    for i in range(len(feats)):
        sig = strategy_eval(feats, i)
        if sig is None:
            continue
        lab = label_signal(feats, i, sig, horizon)
        tp = target_of(sig)
        if lab is None or tp is None:
            continue
        x = row_vector(feats, i, sig.s_tech, float(sig.entry), float(sig.stop), tp)
        rows.append(
            {
                "symbol": symbol,
                "t": feats.index[i],
                "t_end": feats.index[lab.end_idx],
                "y": lab.y,
                **dict(zip(FEATURE_NAMES, x, strict=True)),
            }
        )
    cols = ["symbol", "t", "t_end", "y", *FEATURE_NAMES]
    return pd.DataFrame(rows, columns=cols)
