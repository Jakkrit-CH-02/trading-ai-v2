from __future__ import annotations

from pathlib import Path

import httpx
import joblib
import pytest

from app.clients.backend import BackendClient
from app.datasets.builder import DatasetBuilder
from app.datasets.schemas import BuildRequest, LabelConfig, SplitConfig
from app.features.service import FeatureService
from app.training.schemas import TrainRequest
from app.training.trainer import (
    DatasetNotFound,
    FeaturesNotFound,
    Trainer,
)


def _bars_handler(n_bars: int = 200):
    """A wave with deterministic up/down shape so labels have both classes."""
    import math

    bars = []
    for i in range(n_bars):
        ot = 1_700_000_000_000 + i * 60_000
        # Sine wave around an uptrend → both label classes appear under
        # next_direction labelling.
        price = 100.0 + 0.05 * i + 1.5 * math.sin(i / 5.0)
        bars.append(
            {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "open_time": ot,
                "close_time": ot + 60_000 - 1,
                "open": f"{price - 0.05:.8f}",
                "high": f"{price + 0.20:.8f}",
                "low": f"{price - 0.20:.8f}",
                "close": f"{price:.8f}",
                "volume": f"{1.0 + 0.05 * (i % 7):.8f}",
            }
        )

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"symbol": "BTCUSDT", "interval": "1m", "bars": bars},
        )

    return httpx.MockTransport(handler), bars


async def _build_dataset_and_features(
    tmp_path: Path,
) -> tuple[DatasetBuilder, FeatureService, str]:
    transport, bars = _bars_handler(200)
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
                label=LabelConfig(kind="next_direction", horizon=1),
                split=SplitConfig(train=0.7, val=0.15, test=0.15),
            )
        )
        feat_svc = FeatureService(builder=builder, root=tmp_path / "feat")
        feat_svc.compute(meta.id)
    return builder, feat_svc, meta.id


@pytest.mark.asyncio
async def test_trainer_produces_model_and_metrics(tmp_path: Path) -> None:
    builder, _, dataset_id = await _build_dataset_and_features(tmp_path)
    trainer = Trainer(
        builder=builder,
        features_root=tmp_path / "feat",
        models_root=tmp_path / "models",
    )

    job = trainer.run(TrainRequest(dataset_id=dataset_id, model="logistic_regression"))

    assert job.status == "completed", job.error
    assert job.error is None
    assert job.model_path is not None
    assert job.metadata_path is not None

    # Model artifact actually exists and is loadable.
    model_file = Path(job.model_path)
    assert model_file.exists()
    assert model_file.name == "model.joblib"
    estimator = joblib.load(model_file)
    assert hasattr(estimator, "predict")

    # Metadata sidecar exists and is well-formed.
    meta_file = Path(job.metadata_path)
    assert meta_file.exists()

    # Metrics structure.
    m = job.metrics
    assert m is not None
    assert m.train_rows > 0
    assert m.val_rows > 0
    assert 0.0 <= m.train_accuracy <= 1.0
    assert 0.0 <= m.val_accuracy <= 1.0
    assert set(m.classes).issubset({0, 1})
    assert len(m.classes) >= 2

    # Records features used + window.
    assert len(job.features) > 0
    assert job.window is not None
    assert job.window.from_ms < job.window.to_ms

    # Lookup by id returns the same job.
    fetched = trainer.get(job.id)
    assert fetched is not None
    assert fetched.id == job.id
    assert fetched.status == "completed"


@pytest.mark.asyncio
async def test_trainer_random_forest(tmp_path: Path) -> None:
    builder, _, dataset_id = await _build_dataset_and_features(tmp_path)
    trainer = Trainer(
        builder=builder,
        features_root=tmp_path / "feat",
        models_root=tmp_path / "models",
    )
    job = trainer.run(TrainRequest(dataset_id=dataset_id, model="random_forest"))
    assert job.status == "completed", job.error
    assert job.model_path is not None
    assert Path(job.model_path).exists()


@pytest.mark.asyncio
async def test_trainer_unknown_dataset(tmp_path: Path) -> None:
    transport, _ = _bars_handler(10)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://backend"
    ) as http:
        builder = DatasetBuilder(backend=BackendClient(http), root=tmp_path / "ds")
        trainer = Trainer(
            builder=builder,
            features_root=tmp_path / "feat",
            models_root=tmp_path / "models",
        )
        job = trainer.run(TrainRequest(dataset_id="does-not-exist"))
        assert job.status == "failed"
        assert job.error is not None
        assert "does-not-exist" in job.error


@pytest.mark.asyncio
async def test_trainer_features_missing_for_dataset(tmp_path: Path) -> None:
    transport, bars = _bars_handler(60)
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
        # Features parquet was never computed.
        trainer = Trainer(
            builder=builder,
            features_root=tmp_path / "feat",
            models_root=tmp_path / "models",
        )
        job = trainer.run(TrainRequest(dataset_id=meta.id))
        assert job.status == "failed"
        assert job.error is not None


@pytest.mark.asyncio
async def test_training_api_run_and_get(tmp_path: Path) -> None:
    from fastapi import FastAPI
    from httpx import ASGITransport

    from app.api.training import router as training_router

    builder, _, dataset_id = await _build_dataset_and_features(tmp_path)
    trainer = Trainer(
        builder=builder,
        features_root=tmp_path / "feat",
        models_root=tmp_path / "models",
    )
    app = FastAPI()
    app.state.trainer = trainer
    app.include_router(training_router)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.post(
            "/api/training/run",
            json={"dataset_id": dataset_id, "model": "logistic_regression"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["error"] is None
        job = body["data"]["job"]
        assert job["status"] == "completed"
        job_id = job["id"]

        r2 = await client.get(f"/api/training/{job_id}")
        assert r2.status_code == 200
        assert r2.json()["data"]["job"]["id"] == job_id

        r3 = await client.get("/api/training/missing")
        assert r3.status_code == 404


# Reference dummy assertions to keep imports used when adding new error types.
_ = (DatasetNotFound, FeaturesNotFound)
