"""Indicators vs independent reference implementations.

References are naive pure-Python loops written straight from the textbook (Wilder)
definitions, plus hand-computable analytic cases. They are not TA-Lib output; if TA-Lib
parity is wanted later, add fixtures from it here.
"""

import math
import random
from collections.abc import Callable

import numpy as np
import pandas as pd
import pytest

from app.marketdata import indicators as ind


def _series(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = random.Random(seed)
    price = 100.0
    rows = []
    for _ in range(n):
        o = price
        c = max(1.0, o * (1 + rng.uniform(-0.02, 0.02)))
        h = max(o, c) * (1 + rng.uniform(0, 0.01))
        low = min(o, c) * (1 - rng.uniform(0, 0.01))
        rows.append((o, h, low, c, rng.uniform(100, 1000)))
        price = c
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return pd.DataFrame(rows, columns=["open", "high", "low", "close", "volume"], index=idx)


# ---- naive references --------------------------------------------------------------


def ref_ema(values: list[float], n: int) -> list[float]:
    out = [math.nan] * len(values)
    out[n - 1] = sum(values[:n]) / n
    k = 2 / (n + 1)
    for i in range(n, len(values)):
        out[i] = values[i] * k + out[i - 1] * (1 - k)
    return out


def ref_rsi(values: list[float], n: int) -> list[float]:
    out = [math.nan] * len(values)
    gains = [max(values[i] - values[i - 1], 0.0) for i in range(1, len(values))]
    losses = [max(values[i - 1] - values[i], 0.0) for i in range(1, len(values))]
    ag, al = sum(gains[:n]) / n, sum(losses[:n]) / n
    out[n] = 100 - 100 / (1 + ag / al)
    for i in range(n + 1, len(values)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100 - 100 / (1 + ag / al)
    return out


def ref_atr(h: list[float], low: list[float], c: list[float], n: int) -> list[float]:
    tr = [h[0] - low[0]] + [
        max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1])) for i in range(1, len(c))
    ]
    out = [math.nan] * len(c)
    out[n - 1] = sum(tr[:n]) / n
    for i in range(n, len(c)):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


def ref_adx(h: list[float], low: list[float], c: list[float], n: int) -> list[float]:
    m = len(c)
    pdm, mdm, tr = [0.0] * m, [0.0] * m, [0.0] * m
    for i in range(1, m):
        up, dn = h[i] - h[i - 1], low[i - 1] - low[i]
        pdm[i] = up if up > dn and up > 0 else 0.0
        mdm[i] = dn if dn > up and dn > 0 else 0.0
        tr[i] = max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1]))
    # Wilder running sums seeded with the sum of bars 1..n
    s_tr, s_p, s_m = sum(tr[1 : n + 1]), sum(pdm[1 : n + 1]), sum(mdm[1 : n + 1])
    dx = [math.nan] * m
    dx[n] = 100 * abs(s_p - s_m) / (s_p + s_m)
    for i in range(n + 1, m):
        s_tr = s_tr - s_tr / n + tr[i]
        s_p = s_p - s_p / n + pdm[i]
        s_m = s_m - s_m / n + mdm[i]
        pdi, mdi = 100 * s_p / s_tr, 100 * s_m / s_tr
        dx[i] = 100 * abs(pdi - mdi) / (pdi + mdi)
    out = [math.nan] * m
    first = 2 * n - 1
    out[first] = sum(dx[n : 2 * n]) / n
    for i in range(first + 1, m):
        out[i] = (out[i - 1] * (n - 1) + dx[i]) / n
    return out


def assert_close(actual: pd.Series, expected: list[float], tol: float = 1e-9) -> None:
    np.testing.assert_allclose(actual.to_numpy(), np.array(expected), rtol=tol, atol=tol)


# ---- tests -------------------------------------------------------------------------


@pytest.mark.parametrize("n", [5, 20, 50])
def test_ema_matches_reference(n: int) -> None:
    df = _series()
    assert_close(ind.ema(df["close"], n), ref_ema(df["close"].tolist(), n))


def test_rsi_matches_reference() -> None:
    df = _series()
    assert_close(ind.rsi(df["close"], 14), ref_rsi(df["close"].tolist(), 14))


def test_atr_matches_reference() -> None:
    df = _series()
    got = ind.atr(df["high"], df["low"], df["close"], 14)
    assert_close(got, ref_atr(df["high"].tolist(), df["low"].tolist(), df["close"].tolist(), 14))


def test_adx_matches_reference() -> None:
    df = _series()
    got, _, _ = ind.adx(df["high"], df["low"], df["close"], 14)
    expected = ref_adx(df["high"].tolist(), df["low"].tolist(), df["close"].tolist(), 14)
    assert_close(got, expected, tol=1e-7)


def test_bollinger_hand_computed() -> None:
    # window [1,2,3,4,5]: mean 3, population std sqrt(2)
    close = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    mid, upper, lower, width = ind.bollinger(close, n=5, k=2.0)
    assert mid.iloc[-1] == pytest.approx(3.0)
    assert upper.iloc[-1] == pytest.approx(3.0 + 2 * math.sqrt(2))
    assert lower.iloc[-1] == pytest.approx(3.0 - 2 * math.sqrt(2))
    assert width.iloc[-1] == pytest.approx(4 * math.sqrt(2) / 3.0)
    assert mid.iloc[:4].isna().all()


def test_donchian_and_volume_zscore_hand_computed() -> None:
    high = pd.Series([1.0, 3.0, 2.0, 5.0, 4.0])
    low = pd.Series([0.5, 1.0, 0.8, 2.0, 1.5])
    upper, lower = ind.donchian(high, low, 3)
    assert upper.tolist()[2:] == [3.0, 5.0, 5.0]
    assert lower.tolist()[2:] == [0.5, 0.8, 0.8]
    z = ind.volume_zscore(pd.Series([10.0, 10.0, 10.0, 16.0]), 4)
    # mean 11.5, population std sqrt(6.75)
    assert z.iloc[-1] == pytest.approx((16 - 11.5) / math.sqrt(6.75))


def test_rsi_extremes() -> None:
    rising = pd.Series(np.arange(1.0, 40.0))
    flat = pd.Series([10.0] * 40)
    assert ind.rsi(rising).iloc[-1] == pytest.approx(100.0)
    assert ind.rsi(flat).iloc[-1] == pytest.approx(50.0)


def test_rolling_percentile() -> None:
    s = pd.Series([1.0, 2.0, 3.0, 4.0, 2.5])
    # last value 2.5: values <= 2.5 in window of 5 are 1, 2, 2.5 -> 3/5
    assert ind.rolling_percentile(s, 5).iloc[-1] == pytest.approx(0.6)


def test_too_short_series_is_nan_not_error() -> None:
    short = pd.Series([1.0, 2.0, 3.0])
    assert ind.ema(short, 10).isna().all()
    assert ind.rsi(short, 14).isna().all()


# ---- no look-ahead -----------------------------------------------------------------

_CAUSAL: dict[str, Callable[[pd.DataFrame], pd.Series]] = {
    "ema": lambda d: ind.ema(d["close"], 20),
    "rsi": lambda d: ind.rsi(d["close"], 14),
    "atr": lambda d: ind.atr(d["high"], d["low"], d["close"], 14),
    "adx": lambda d: ind.adx(d["high"], d["low"], d["close"], 14)[0],
    "bb_width": lambda d: ind.bollinger(d["close"], 20)[3],
    "bb_pct": lambda d: ind.rolling_percentile(ind.bollinger(d["close"], 20)[3], 50),
    "donchian": lambda d: ind.donchian(d["high"], d["low"], 20)[0],
    "vol_z": lambda d: ind.volume_zscore(d["volume"], 20),
}


@pytest.mark.parametrize("name", sorted(_CAUSAL))
def test_indicator_has_no_lookahead(name: str) -> None:
    """Value at bar t must not change when bars after t are removed."""
    df = _series(250)
    full = _CAUSAL[name](df)
    for cut in (100, 150, 200):
        part = _CAUSAL[name](df.iloc[:cut])
        np.testing.assert_allclose(
            part.to_numpy(), full.iloc[:cut].to_numpy(), rtol=1e-12, atol=1e-12, equal_nan=True
        )
