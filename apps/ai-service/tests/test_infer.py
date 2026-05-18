from __future__ import annotations

import numpy as np
import pytest
import httpx
from fastapi import FastAPI
from httpx import ASGITransport
from pathlib import Path

from app.api.infer import router as infer_router
from app.inference.service import InferenceService
from app.registry.service import RegistryService
from app.registry.store import ModelStore


# ---------- helpers ----------

def _make_bar(i: int) -> dict:
    """Generate a synthetic OHLCV bar dict. Close alternates above/below 100."""
    close = 100.0 + float(i % 5)
    return {
        "open_time": 1_700_000_000_000 + i * 60_000,
        "open":   close - 0.1,
        "high":   close + 0.5,
        "low":    close - 0.5,
        "close":  close,
        "volume": 1000.0 + float(i),
    }


def _sixty_bars() -> list[dict]:
    return [_make_bar(i) for i in range(60)]


class _StubEstimator:
    classes_ = np.array([0, 1])

    def predict_proba(self, X):  # noqa: N803
        # sum > 0 → BUY, sum < 0 → SELL, else HOLD
        out = []
        for row in X:
            s = float(np.sum(row))
            if s > 5.0:
                out.append([0.15, 0.85])
            elif s < -5.0:
                out.append([0.85, 0.15])
            else:
                out.append([0.52, 0.48])
        return np.array(out)


def _app_with_model(tmp_path: Path) -> FastAPI:
    store = ModelStore(root=tmp_path / "models")
    registry = RegistryService(store=store)
    from app.features.registry import DEFAULT_FEATURES
    meta = registry.register(
        estimator=_StubEstimator(),
        dataset_id="ds-test",
        feature_names=list(DEFAULT_FEATURES),
        evaluated=True,
    )
    registry.promote(meta.id, "paper")
    inf = InferenceService(registry=registry, environment="paper")
    inf.load()
    app = FastAPI()
    app.state.inference = inf
    app.include_router(infer_router)
    return app


def _app_no_model(tmp_path: Path) -> FastAPI:
    store = ModelStore(root=tmp_path / "models")
    inf = InferenceService(registry=RegistryService(store=store), environment="paper")
    inf.load()
    app = FastAPI()
    app.state.inference = inf
    app.include_router(infer_router)
    return app


# ---------- tests ----------

@pytest.mark.asyncio
async def test_infer_hold_when_no_model(tmp_path: Path) -> None:
    app = _app_no_model(tmp_path)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/infer", json={"symbol": "BTCUSDT", "interval": "1m", "bars": _sixty_bars()})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["action"] == "hold"
    assert data["confidence"] == 0.0
    assert data["model_version"] == ""


@pytest.mark.asyncio
async def test_infer_hold_when_too_few_bars(tmp_path: Path) -> None:
    app = _app_with_model(tmp_path)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/infer", json={
            "symbol": "BTCUSDT",
            "interval": "1m",
            "bars": [_make_bar(i) for i in range(10)],  # only 10 bars — below 34 minimum
        })
    assert r.status_code == 200
    assert r.json()["data"]["action"] == "hold"


@pytest.mark.asyncio
async def test_infer_returns_signal_with_60_bars(tmp_path: Path) -> None:
    app = _app_with_model(tmp_path)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/infer", json={"symbol": "BTCUSDT", "interval": "1m", "bars": _sixty_bars()})
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["action"] in ("buy", "sell", "hold")
    assert 0.0 <= data["confidence"] <= 1.0
    assert isinstance(data["model_version"], str)


@pytest.mark.asyncio
async def test_infer_validation_error_on_empty_bars(tmp_path: Path) -> None:
    app = _app_with_model(tmp_path)
    async with httpx.AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        r = await c.post("/v1/infer", json={"symbol": "BTCUSDT", "interval": "1m", "bars": []})
    assert r.status_code == 200  # empty bars → HOLD, not an error
    assert r.json()["data"]["action"] == "hold"
