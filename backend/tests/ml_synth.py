"""Synthetic labelled-signal frames for the ML tests."""

import numpy as np
import pandas as pd

from app.ml.features import FEATURE_NAMES


def synth_dataset(
    n: int = 500, informative: bool = True, seed: int = 1, hold_h: int = 12
) -> pd.DataFrame:
    """``n`` signals, one per 3 hours, labels resolving ``hold_h`` hours later. With
    ``informative`` the win probability rises with ``rsi14``; otherwise labels are coin flips."""
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(n, len(FEATURE_NAMES)))
    if informative:
        p = 1 / (1 + np.exp(-(2.5 * x[:, FEATURE_NAMES.index("rsi14")] - 1.0)))
    else:
        p = np.full(n, 0.3)
    y = (rng.random(n) < p).astype(int)
    t = pd.date_range("2024-01-01", periods=n, freq="3h", tz="UTC")
    df = pd.DataFrame(x, columns=FEATURE_NAMES)
    df.insert(0, "y", y)
    df.insert(0, "t_end", t + pd.Timedelta(hours=hold_h))
    df.insert(0, "t", t)
    df.insert(0, "symbol", np.where(np.arange(n) % 2 == 0, "BTCUSDT", "ETHUSDT"))
    return df
