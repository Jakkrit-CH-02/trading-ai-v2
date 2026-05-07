from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport, MockTransport

from app.api.evaluation import router as evaluation_router
from app.clients.backend import BackendClient
from app.evaluation.schemas import EvaluationMetrics
from app.evaluation.service import (
    BacktestNotFound,
    EvaluationService,
    compute_metrics,
)
from app.registry.service import RegistryService
from app.registry.store import ModelNotFound, ModelStore


# Deterministic fixture: 4 closed trades (3 wins, 1 loss) and a 5-point
# equity curve whose returns split-half drift is exactly computable.
FIXTURE_BACKTEST = {
    "id": "bt-fixture",
    "config": {"symbol": "BTCUSDT", "interval": "5m"},
    "start_ms": 1_700_000_000_000,
    "end_ms": 1_700_000_240_000,
    "bars_processed": 5,
    "initial_equity": "1000",
    "final_equity": "1075",
    "metrics": {},
    "equity_curve": [
        {"timestamp_ms": 1_700_000_000_000, "equity": "1000"},
        {"timestamp_ms": 1_700_000_060_000, "equity": "1010"},
        {"timestamp_ms": 1_700_000_120_000, "equity": "1005"},
        {"timestamp_ms": 1_700_000_180_000, "equity": "1050"},
        {"timestamp_ms": 1_700_000_240_000, "equity": "1075"},
    ],
    "trades": [
        {"side": "BUY", "realized_pl": "0", "price": "100", "qty": "1"},
        {"side": "SELL", "realized_pl": "10", "price": "110", "qty": "1"},
        {"side": "BUY", "realized_pl": "0", "price": "108", "qty": "1"},
        {"side": "SELL", "realized_pl": "-5", "price": "103", "qty": "1"},
        {"side": "BUY", "realized_pl": "0", "price": "104", "qty": "1"},
        {"side": "SELL", "realized_pl": "45", "price": "149", "qty": "1"},
        {"side": "BUY", "realized_pl": "0", "price": "150", "qty": "1"},
        {"side": "SELL", "realized_pl": "25", "price": "175", "qty": "1"},
    ],
    "created_ms": 1_700_000_240_000,
}


def _make_backend(payload: dict | None) -> BackendClient:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/api/backtest/"):
            if payload is None:
                return httpx.Response(404, json={"data": None, "error": {"code": "not_found", "message": "x"}})
            return httpx.Response(200, json={"data": payload, "error": None})
        return httpx.Response(404)

    transport = MockTransport(handler)
    client = httpx.AsyncClient(transport=transport, base_url="http://backend.test")
    return BackendClient(client)


class _Stub:
    def predict_proba(self, X):  # noqa: N803
        return [[0.5, 0.5] for _ in X]


def _registry_with_model(tmp_path: Path) -> tuple[RegistryService, str]:
    store = ModelStore(root=tmp_path / "models")
    svc = RegistryService(store=store)

    meta = svc.register(
        estimator=_Stub(),
        dataset_id="ds-eval",
        feature_names=["rsi_14"],
        evaluated=False,
    )
    return svc, meta.id


def test_compute_metrics_deterministic() -> None:
    m = compute_metrics(FIXTURE_BACKTEST)
    assert m.total_trades == 4
    assert m.winning_trades == 3
    assert m.losing_trades == 1
    assert m.precision == pytest.approx(0.75)
    # equity returns: +1.0%, -0.495%, +4.478%, +2.381% — 3 positive bars
    assert m.recall == pytest.approx(1.0)
    assert m.calibration_error == pytest.approx(0.25)
    # split-half drift: |mean(first 2) - mean(last 2)| / stddev(all 4)
    returns = [
        (1010 - 1000) / 1000,
        (1005 - 1010) / 1010,
        (1050 - 1005) / 1005,
        (1075 - 1050) / 1050,
    ]
    mean_a = (returns[0] + returns[1]) / 2
    mean_b = (returns[2] + returns[3]) / 2
    mean_all = sum(returns) / 4
    var = sum((r - mean_all) ** 2 for r in returns) / 3
    sd = var**0.5
    expected_drift = abs(mean_a - mean_b) / sd
    assert m.feature_drift == pytest.approx(expected_drift)


@pytest.mark.asyncio
async def test_run_evaluation_persists_report(tmp_path: Path) -> None:
    registry, mid = _registry_with_model(tmp_path)
    backend = _make_backend(FIXTURE_BACKTEST)
    svc = EvaluationService(backend=backend, registry=registry)

    rep = await svc.run(backtest_id="bt-fixture", model_id=mid)
    assert rep.passed is True
    assert rep.symbol == "BTCUSDT"
    assert rep.interval == "5m"
    assert rep.metrics.precision == pytest.approx(0.75)
    assert rep.reason.startswith("precision 0.750")

    # Stored, retrievable by id
    again = svc.get(rep.id)
    assert again == rep

    # Pass should mark the model as evaluated for live promotion gate.
    assert registry.get(mid).evaluated is True


@pytest.mark.asyncio
async def test_run_evaluation_fails_when_no_trades(tmp_path: Path) -> None:
    registry, mid = _registry_with_model(tmp_path)
    empty = {**FIXTURE_BACKTEST, "trades": [], "equity_curve": []}
    svc = EvaluationService(backend=_make_backend(empty), registry=registry)

    rep = await svc.run(backtest_id="bt-empty", model_id=mid)
    assert rep.passed is False
    assert rep.reason == "no closed trades"
    assert rep.metrics.total_trades == 0
    # Failed evaluation must not flip the registry's `evaluated` flag.
    assert registry.get(mid).evaluated is False


@pytest.mark.asyncio
async def test_run_evaluation_unknown_model(tmp_path: Path) -> None:
    store = ModelStore(root=tmp_path / "models")
    registry = RegistryService(store=store)
    svc = EvaluationService(backend=_make_backend(FIXTURE_BACKTEST), registry=registry)

    with pytest.raises(ModelNotFound):
        await svc.run(backtest_id="bt-fixture", model_id="missing-model")


@pytest.mark.asyncio
async def test_run_evaluation_missing_backtest(tmp_path: Path) -> None:
    registry, mid = _registry_with_model(tmp_path)
    # Backend returns the envelope but `data` is empty {} — service treats as not found.
    svc = EvaluationService(backend=_make_backend({}), registry=registry)
    with pytest.raises(BacktestNotFound):
        await svc.run(backtest_id="bt-missing", model_id=mid)


@pytest.mark.asyncio
async def test_api_run_and_get(tmp_path: Path) -> None:
    registry, mid = _registry_with_model(tmp_path)
    backend = _make_backend(FIXTURE_BACKTEST)
    svc = EvaluationService(backend=backend, registry=registry)

    app = FastAPI()
    app.state.evaluation = svc
    app.include_router(evaluation_router)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/evaluation/run",
            json={"backtest_id": "bt-fixture", "model_id": mid},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["error"] is None
        data = body["data"]
        assert data["passed"] is True
        assert data["model_id"] == mid
        assert data["backtest_id"] == "bt-fixture"
        assert data["metrics"]["precision"] == pytest.approx(0.75)
        eval_id = data["id"]

        r2 = await client.get(f"/api/evaluation/{eval_id}")
        assert r2.status_code == 200
        data2 = r2.json()["data"]
        assert data2["id"] == eval_id
        assert data2["metrics"]["winning_trades"] == 3


@pytest.mark.asyncio
async def test_api_get_unknown(tmp_path: Path) -> None:
    registry, _ = _registry_with_model(tmp_path)
    svc = EvaluationService(backend=_make_backend(FIXTURE_BACKTEST), registry=registry)

    app = FastAPI()
    app.state.evaluation = svc
    app.include_router(evaluation_router)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/evaluation/nope")
        assert r.status_code == 404
        assert r.json()["detail"]["error"]["code"] == "not_found"


def test_metrics_schema_is_jsonable() -> None:
    m = EvaluationMetrics(
        total_trades=0,
        winning_trades=0,
        losing_trades=0,
        precision=0.0,
        recall=0.0,
        calibration_error=0.5,
        feature_drift=0.0,
    )
    assert m.model_dump()["calibration_error"] == 0.5
