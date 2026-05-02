from __future__ import annotations

from pathlib import Path

import httpx
import pandas as pd
import pytest

from app.clients.backend import BackendClient
from app.datasets.builder import DatasetBuilder
from app.datasets.schemas import BuildRequest
from app.features.pipeline import compute_features
from app.features.registry import DEFAULT_FEATURES, REGISTRY
from app.features.service import DatasetNotFound, FeatureService


def _fixed_input_df(n: int = 60) -> pd.DataFrame:
    """Deterministic OHLCV — sinusoidal close around a slow uptrend.

    Money fields are strings (matches dataset parquet convention).
    """
    import math

    rows = []
    for i in range(n):
        # Closed-form, no RNG → same on every machine.
        close = 100.0 + 0.5 * i + 2.0 * math.sin(i / 3.0)
        rows.append(
            {
                "open_time": 1_700_000_000_000 + i * 60_000,
                "open": f"{close - 0.10:.8f}",
                "high": f"{close + 0.30:.8f}",
                "low": f"{close - 0.40:.8f}",
                "close": f"{close:.8f}",
                "volume": f"{1.0 + 0.05 * (i % 7):.8f}",
            }
        )
    return pd.DataFrame(rows)


# Golden values were captured from the deterministic input above and
# pinned here so any unintended drift in the math fails loudly.
GOLDEN_FIRST_ROW = {
    "return_1": 0.0034424740136764775,
    "return_5": 0.0027796268799822332,
    "ema_12": 113.23291970244273,
    "ema_26": 110.60171957633995,
    "rsi_14": 93.64300314645905,
    "macd": 2.631200126102783,
    "macd_signal": 2.8769139719829906,
    "macd_hist": -0.2457138458802075,
    "atr_14": 0.8496452243751588,
    "bb_upper": 118.12474128710117,
    "bb_lower": 105.14556398089881,
    "bb_width": 0.11626425010368442,
    "volatility_20": 0.004189654671341739,
    "volume_zscore_20": 1.1136010553738926,
}
GOLDEN_ROW_COUNT = 27


def test_default_feature_order_is_stable() -> None:
    assert DEFAULT_FEATURES == (
        "return_1",
        "return_5",
        "ema_12",
        "ema_26",
        "rsi_14",
        "macd",
        "macd_signal",
        "macd_hist",
        "atr_14",
        "bb_upper",
        "bb_lower",
        "bb_width",
        "volatility_20",
        "volume_zscore_20",
    )
    # registry order matches default order
    assert tuple(REGISTRY.keys()) == DEFAULT_FEATURES


def test_compute_features_matches_golden_snapshot() -> None:
    df = _fixed_input_df(60)
    feat = compute_features(df)

    # Stable column order: open_time + DEFAULT_FEATURES.
    assert list(feat.columns) == ["open_time"] + list(DEFAULT_FEATURES)
    # Warm-up rows dropped → no NaNs left.
    assert not feat.isna().any().any()
    assert len(feat) == GOLDEN_ROW_COUNT
    assert feat["open_time"].is_monotonic_increasing

    first = feat.iloc[0]
    for name, expected in GOLDEN_FIRST_ROW.items():
        actual = float(first[name])
        assert actual == pytest.approx(expected, rel=1e-5, abs=1e-6), (
            f"{name}: got {actual}, expected {expected}"
        )


def test_compute_features_subset_and_order() -> None:
    df = _fixed_input_df(40)
    feat = compute_features(df, ["rsi_14", "ema_12"])
    assert list(feat.columns) == ["open_time", "rsi_14", "ema_12"]


def test_compute_features_rejects_unknown_name() -> None:
    df = _fixed_input_df(40)
    with pytest.raises(ValueError, match="unknown features"):
        compute_features(df, ["nope"])


# ---------- service / API wiring ----------


def _make_transport(n_bars: int = 80):
    bars = []
    for i in range(n_bars):
        ot = 1_700_000_000_000 + i * 60_000
        price = 100 + i * 0.5
        bars.append(
            {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "open_time": ot,
                "close_time": ot + 60_000 - 1,
                "open": f"{price:.8f}",
                "high": f"{price + 0.25:.8f}",
                "low": f"{price - 0.25:.8f}",
                "close": f"{price + 0.10:.8f}",
                "volume": "1.50000000",
            }
        )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"symbol": "BTCUSDT", "interval": "1m", "bars": bars},
        )

    return httpx.MockTransport(handler), bars


@pytest.mark.asyncio
async def test_feature_service_writes_parquet(tmp_path: Path) -> None:
    transport, bars = _make_transport(80)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://backend"
    ) as http:
        builder = DatasetBuilder(backend=BackendClient(http), root=tmp_path / "ds")
        meta = await builder.build(
            BuildRequest(
                symbol="BTCUSDT",
                timeframe="1m",
                from_ms=bars[0]["open_time"],
                to_ms=bars[-1]["open_time"] + 60_000,
            )
        )
        svc = FeatureService(builder=builder, root=tmp_path / "feat")
        result = svc.compute(meta.id)

    out = Path(result.path)
    assert out.exists()
    assert out.name == f"{meta.id}.parquet"
    feat = pd.read_parquet(out)
    assert list(feat.columns) == ["open_time"] + list(DEFAULT_FEATURES)
    assert result.rows == len(feat)
    assert result.features == list(DEFAULT_FEATURES)


@pytest.mark.asyncio
async def test_feature_service_unknown_dataset(tmp_path: Path) -> None:
    transport, _ = _make_transport(10)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://backend"
    ) as http:
        builder = DatasetBuilder(backend=BackendClient(http), root=tmp_path / "ds")
        svc = FeatureService(builder=builder, root=tmp_path / "feat")
        with pytest.raises(DatasetNotFound):
            svc.compute("does-not-exist")
