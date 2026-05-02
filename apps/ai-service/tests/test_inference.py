from __future__ import annotations

import time
from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.predict import router as predict_router
from app.inference.schemas import PredictRequest
from app.inference.service import (
    FeatureSchemaMismatch,
    InferenceService,
    ModelUnavailable,
)
from app.registry.service import RegistryService
from app.registry.store import ModelStore


class _StubEstimator:
    """Deterministic stand-in for a fitted classifier.

    Exposes the sklearn-like interface the InferenceService needs
    (`classes_`, `predict_proba`) so the golden output is fully predictable
    without depending on sklearn's solver behaviour.
    """

    classes_ = np.array([0, 1])

    def predict_proba(self, X):  # noqa: N803 - sklearn convention
        out = []
        for row in X:
            s = float(np.sum(row))
            if s > 1.0:
                out.append([0.18, 0.82])  # strong BUY
            elif s < -1.0:
                out.append([0.85, 0.15])  # strong SELL
            else:
                out.append([0.55, 0.45])  # HOLD band
        return np.asarray(out)


def _registry_with_active(tmp_path: Path) -> tuple[RegistryService, str]:
    store = ModelStore(root=tmp_path / "models")
    svc = RegistryService(store=store)
    meta = svc.register(
        estimator=_StubEstimator(),
        dataset_id="ds-golden",
        feature_names=["rsi_14", "ema_trend", "volume_ratio"],
        evaluated=True,
    )
    svc.promote(meta.id, "paper")
    return svc, meta.id


def test_predict_golden_buy(tmp_path: Path) -> None:
    registry, mid = _registry_with_active(tmp_path)
    inf = InferenceService(registry=registry, environment="paper", cache_ttl_s=5.0)
    assert inf.load() is True
    assert inf.model_id == mid
    assert inf.model_version == 1

    req = PredictRequest(
        symbol="BTCUSDT",
        timeframe="5m",
        features={"rsi_14": 0.5, "ema_trend": 0.6, "volume_ratio": 0.7},
    )
    resp = inf.predict(req)

    # Golden: stub returns [0.18, 0.82] when sum > 1.0 (here sum = 1.8).
    assert resp.signal == "BUY"
    assert resp.confidence == pytest.approx(0.82)
    assert resp.risk_score == pytest.approx(0.18)
    assert resp.probabilities == {"0": pytest.approx(0.18), "1": pytest.approx(0.82)}
    assert resp.model_id == mid
    assert resp.model_version == 1
    assert resp.symbol == "BTCUSDT"
    assert resp.timeframe == "5m"
    assert resp.cached is False


def test_predict_golden_sell_and_hold(tmp_path: Path) -> None:
    registry, _ = _registry_with_active(tmp_path)
    inf = InferenceService(registry=registry, environment="paper", cache_ttl_s=5.0)
    inf.load()

    sell = inf.predict(
        PredictRequest(
            symbol="BTCUSDT",
            timeframe="5m",
            features={"rsi_14": -1.0, "ema_trend": -0.5, "volume_ratio": -0.5},
        )
    )
    assert sell.signal == "SELL"
    assert sell.confidence == pytest.approx(0.85)

    hold = inf.predict(
        PredictRequest(
            symbol="BTCUSDT",
            timeframe="5m",
            features={"rsi_14": 0.1, "ema_trend": 0.2, "volume_ratio": 0.3},
        )
    )
    assert hold.signal == "HOLD"
    assert hold.probabilities == {"0": pytest.approx(0.55), "1": pytest.approx(0.45)}


def test_cache_hit_for_identical_input(tmp_path: Path) -> None:
    registry, _ = _registry_with_active(tmp_path)
    inf = InferenceService(registry=registry, environment="paper", cache_ttl_s=5.0)
    inf.load()

    req = PredictRequest(
        symbol="BTCUSDT",
        timeframe="5m",
        features={"rsi_14": 0.5, "ema_trend": 0.6, "volume_ratio": 0.7},
    )
    first = inf.predict(req)
    second = inf.predict(req)
    assert first.cached is False
    assert second.cached is True
    assert second.signal == first.signal
    assert second.confidence == first.confidence


def test_cache_expires(tmp_path: Path) -> None:
    registry, _ = _registry_with_active(tmp_path)
    inf = InferenceService(registry=registry, environment="paper", cache_ttl_s=0.05)
    inf.load()
    req = PredictRequest(
        symbol="BTCUSDT",
        timeframe="5m",
        features={"rsi_14": 0.5, "ema_trend": 0.6, "volume_ratio": 0.7},
    )
    inf.predict(req)
    time.sleep(0.1)
    again = inf.predict(req)
    assert again.cached is False


def test_feature_schema_mismatch(tmp_path: Path) -> None:
    registry, _ = _registry_with_active(tmp_path)
    inf = InferenceService(registry=registry, environment="paper")
    inf.load()
    with pytest.raises(FeatureSchemaMismatch):
        inf.predict(
            PredictRequest(
                symbol="BTCUSDT",
                timeframe="5m",
                features={"rsi_14": 0.5},  # missing ema_trend, volume_ratio
            )
        )


def test_predict_unloaded_raises(tmp_path: Path) -> None:
    store = ModelStore(root=tmp_path / "models")
    inf = InferenceService(registry=RegistryService(store=store), environment="paper")
    assert inf.load() is False
    assert inf.loaded is False
    with pytest.raises(ModelUnavailable):
        inf.predict(
            PredictRequest(
                symbol="BTCUSDT", timeframe="5m", features={"rsi_14": 0.5}
            )
        )


def test_reload_picks_up_new_active(tmp_path: Path) -> None:
    store = ModelStore(root=tmp_path / "models")
    registry = RegistryService(store=store)
    inf = InferenceService(registry=registry, environment="paper")
    assert inf.load() is False  # no active yet

    m1 = registry.register(
        estimator=_StubEstimator(),
        dataset_id="ds-1",
        feature_names=["rsi_14", "ema_trend", "volume_ratio"],
    )
    registry.promote(m1.id, "paper")
    assert inf.reload() is True
    assert inf.model_id == m1.id

    m2 = registry.register(
        estimator=_StubEstimator(),
        dataset_id="ds-1",
        feature_names=["rsi_14", "ema_trend", "volume_ratio"],
    )
    registry.promote(m2.id, "paper")
    inf.reload()
    assert inf.model_id == m2.id
    assert inf.model_version == 2


@pytest.mark.asyncio
async def test_api_predict_golden(tmp_path: Path) -> None:
    registry, mid = _registry_with_active(tmp_path)
    inf = InferenceService(registry=registry, environment="paper", cache_ttl_s=5.0)
    inf.load()

    app = FastAPI()
    app.state.inference = inf
    app.include_router(predict_router)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/predict",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "features": {"rsi_14": 0.5, "ema_trend": 0.6, "volume_ratio": 0.7},
            },
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["error"] is None
        data = body["data"]
        assert data["signal"] == "BUY"
        assert data["confidence"] == pytest.approx(0.82)
        assert data["risk_score"] == pytest.approx(0.18)
        assert data["model_id"] == mid
        assert data["model_version"] == 1


@pytest.mark.asyncio
async def test_api_predict_model_unavailable(tmp_path: Path) -> None:
    store = ModelStore(root=tmp_path / "models")
    inf = InferenceService(registry=RegistryService(store=store), environment="paper")
    inf.load()

    app = FastAPI()
    app.state.inference = inf
    app.include_router(predict_router)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/predict",
            json={
                "symbol": "BTCUSDT",
                "timeframe": "5m",
                "features": {"rsi_14": 0.5},
            },
        )
        assert r.status_code == 503
        detail = r.json()["detail"]
        assert detail["error"]["code"] == "model_unavailable"
        assert detail["data"]["signal"] == "HOLD"


@pytest.mark.asyncio
async def test_api_reload(tmp_path: Path) -> None:
    registry, mid = _registry_with_active(tmp_path)
    inf = InferenceService(registry=registry, environment="paper")

    app = FastAPI()
    app.state.inference = inf
    app.include_router(predict_router)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post("/api/predict/reload")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["loaded"] is True
        assert data["model_id"] == mid
        assert data["environment"] == "paper"
