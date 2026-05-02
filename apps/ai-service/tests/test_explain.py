from __future__ import annotations

from pathlib import Path

import httpx
import numpy as np
import pytest
from fastapi import FastAPI
from httpx import ASGITransport

from app.api.predict import router as predict_router
from app.explain.service import Explanation, build_explanation
from app.inference.schemas import PredictRequest
from app.inference.service import InferenceService
from app.registry.service import RegistryService
from app.registry.store import ModelStore


class _StubEstimator:
    classes_ = np.array([0, 1])

    def predict_proba(self, X):  # noqa: N803
        out = []
        for row in X:
            s = float(np.sum(row))
            if s > 1.0:
                out.append([0.18, 0.82])
            elif s < -1.0:
                out.append([0.85, 0.15])
            else:
                out.append([0.55, 0.45])
        return np.asarray(out)


class _ImportanceStub(_StubEstimator):
    feature_importances_ = np.array([0.1, 0.6, 0.3])


def _registry(tmp_path: Path, estimator) -> tuple[RegistryService, str]:
    store = ModelStore(root=tmp_path / "models")
    svc = RegistryService(store=store)
    meta = svc.register(
        estimator=estimator,
        dataset_id="ds-explain",
        feature_names=["rsi_14", "ema_trend", "volume_ratio"],
        evaluated=True,
    )
    svc.promote(meta.id, "paper")
    return svc, meta.id


def test_build_explanation_uniform_fallback() -> None:
    exp = build_explanation(
        estimator=_StubEstimator(),
        feature_names=["rsi_14", "ema_trend", "volume_ratio"],
        values=[0.5, 0.6, 0.7],
        signal="BUY",
        confidence=0.82,
    )
    assert isinstance(exp, Explanation)
    # uniform 1/3 importance → ranking by raw value
    assert exp.top_features == ["volume_ratio", "ema_trend", "rsi_14"]
    assert len(exp.contributions) == 3
    assert exp.contributions[0].importance == pytest.approx(1.0 / 3.0)
    assert exp.contributions[2].contribution == pytest.approx(0.7 / 3.0)
    assert "BUY" in exp.reason
    assert "high" in exp.confidence_explanation


def test_build_explanation_uses_feature_importances() -> None:
    exp = build_explanation(
        estimator=_ImportanceStub(),
        feature_names=["rsi_14", "ema_trend", "volume_ratio"],
        values=[0.5, 0.6, 0.7],
        signal="BUY",
        confidence=0.82,
    )
    # contributions: 0.05, 0.36, 0.21 → ema_trend, volume_ratio, rsi_14
    assert exp.top_features == ["ema_trend", "volume_ratio", "rsi_14"]
    cmap = {c.name: c for c in exp.contributions}
    assert cmap["ema_trend"].contribution == pytest.approx(0.6 * 0.6)
    assert cmap["volume_ratio"].contribution == pytest.approx(0.7 * 0.3)
    assert cmap["rsi_14"].contribution == pytest.approx(0.5 * 0.1)


def test_build_explanation_is_deterministic() -> None:
    args = dict(
        estimator=_ImportanceStub(),
        feature_names=["rsi_14", "ema_trend", "volume_ratio"],
        values=[0.5, 0.6, 0.7],
        signal="BUY",
        confidence=0.82,
    )
    a = build_explanation(**args)
    b = build_explanation(**args)
    assert a.model_dump() == b.model_dump()


def test_predict_omits_explanation_by_default(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path, _StubEstimator())
    inf = InferenceService(registry=registry, environment="paper", cache_ttl_s=5.0)
    inf.load()
    req = PredictRequest(
        symbol="BTCUSDT",
        timeframe="5m",
        features={"rsi_14": 0.5, "ema_trend": 0.6, "volume_ratio": 0.7},
    )
    resp = inf.predict(req)
    assert resp.explanation is None


def test_predict_attaches_explanation_when_requested(tmp_path: Path) -> None:
    registry, _ = _registry(tmp_path, _ImportanceStub())
    inf = InferenceService(registry=registry, environment="paper", cache_ttl_s=5.0)
    inf.load()
    req = PredictRequest(
        symbol="BTCUSDT",
        timeframe="5m",
        features={"rsi_14": 0.5, "ema_trend": 0.6, "volume_ratio": 0.7},
    )
    resp = inf.predict(req, explain=True)
    assert resp.signal == "BUY"
    assert resp.explanation is not None
    assert resp.explanation.top_features == ["ema_trend", "volume_ratio", "rsi_14"]
    assert len(resp.explanation.contributions) == 3


@pytest.mark.asyncio
async def test_api_predict_explain_query_param(tmp_path: Path) -> None:
    registry, mid = _registry(tmp_path, _ImportanceStub())
    inf = InferenceService(registry=registry, environment="paper", cache_ttl_s=5.0)
    inf.load()

    app = FastAPI()
    app.state.inference = inf
    app.include_router(predict_router)

    body = {
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "features": {"rsi_14": 0.5, "ema_trend": 0.6, "volume_ratio": 0.7},
    }
    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        plain = await client.post("/api/predict", json=body)
        assert plain.status_code == 200
        assert plain.json()["data"]["explanation"] is None

        explained = await client.post("/api/predict?explain=true", json=body)
        assert explained.status_code == 200
        ex = explained.json()["data"]["explanation"]
        assert ex is not None
        assert ex["top_features"] == ["ema_trend", "volume_ratio", "rsi_14"]
        assert len(ex["contributions"]) == 3
        assert ex["confidence_explanation"].startswith("confidence is high")
        assert ex["contributions"][0]["name"] == "rsi_14"
        # Same input yields identical explanation across calls.
        again = await client.post("/api/predict?explain=true", json=body)
        assert again.json()["data"]["explanation"] == ex
        assert again.json()["data"]["model_id"] == mid
