from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from httpx import ASGITransport
from sklearn.linear_model import LogisticRegression

from app.api.models import router as models_router
from app.registry.service import RegistryService
from app.registry.store import ModelNotFound, ModelStore, NotEvaluated


def _fit_dummy() -> LogisticRegression:
    clf = LogisticRegression()
    clf.fit([[0.0], [1.0], [2.0], [3.0]], [0, 0, 1, 1])
    return clf


def test_register_two_versions_and_promote(tmp_path: Path) -> None:
    svc = RegistryService(store=ModelStore(root=tmp_path / "models"))

    v1 = svc.register(
        estimator=_fit_dummy(),
        dataset_id="ds-1",
        feature_schema_id="fs-1",
        metrics={"val_accuracy": 0.6},
        evaluated=False,
    )
    v2 = svc.register(
        estimator=_fit_dummy(),
        dataset_id="ds-1",
        feature_schema_id="fs-1",
        metrics={"val_accuracy": 0.71},
        evaluated=True,
    )

    assert v1.id != v2.id
    assert v1.version == 1
    assert v2.version == 2
    assert Path(v1.artifact_path).exists()
    assert Path(v2.artifact_path).exists()
    assert (tmp_path / "models" / v1.id / "metadata.json").exists()

    listed = svc.list()
    assert [m.id for m in listed] == [v1.id, v2.id]

    # Initially nothing active.
    initial = svc.active()
    assert initial.paper is None
    assert initial.live is None

    # Promote v2 to paper.
    after_paper = svc.promote(v2.id, "paper")
    assert after_paper.paper == v2.id
    assert after_paper.live is None
    assert svc.active().paper == v2.id

    # Promote v2 to live (allowed because evaluated=True).
    after_live = svc.promote(v2.id, "live")
    assert after_live.paper == v2.id
    assert after_live.live == v2.id
    assert svc.active().live == v2.id

    # Live promotion is gated on evaluation.
    with pytest.raises(NotEvaluated):
        svc.promote(v1.id, "live")
    # Paper promotion of v1 is allowed and replaces the active paper model.
    after_paper_v1 = svc.promote(v1.id, "paper")
    assert after_paper_v1.paper == v1.id
    assert after_paper_v1.live == v2.id

    # Unknown id surfaces a typed error.
    with pytest.raises(ModelNotFound):
        svc.promote("does-not-exist", "paper")


@pytest.mark.asyncio
async def test_models_api_list_and_promote(tmp_path: Path) -> None:
    svc = RegistryService(store=ModelStore(root=tmp_path / "models"))
    v1 = svc.register(estimator=_fit_dummy(), dataset_id="ds-1")
    v2 = svc.register(
        estimator=_fit_dummy(),
        dataset_id="ds-1",
        metrics={"val_accuracy": 0.8},
        evaluated=True,
    )

    app = FastAPI()
    app.state.registry = svc
    app.include_router(models_router)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        r = await client.get("/api/models")
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["error"] is None
        ids = [m["id"] for m in body["data"]["models"]]
        assert ids == [v1.id, v2.id]
        assert body["data"]["active"] == {"paper": None, "live": None}

        # Promote v2 to paper, then live.
        r2 = await client.post(
            f"/api/models/{v2.id}/promote", json={"environment": "paper"}
        )
        assert r2.status_code == 200, r2.text
        assert r2.json()["data"]["active"]["paper"] == v2.id
        assert r2.json()["data"]["active"]["live"] is None

        r3 = await client.post(
            f"/api/models/{v2.id}/promote", json={"environment": "live"}
        )
        assert r3.status_code == 200, r3.text
        active = r3.json()["data"]["active"]
        assert active["paper"] == v2.id
        assert active["live"] == v2.id

        # v1 is not evaluated → live promotion rejected.
        r4 = await client.post(
            f"/api/models/{v1.id}/promote", json={"environment": "live"}
        )
        assert r4.status_code == 400
        assert r4.json()["detail"]["error"]["code"] == "validation_failed"

        # Unknown id → 404.
        r5 = await client.post(
            "/api/models/missing/promote", json={"environment": "paper"}
        )
        assert r5.status_code == 404
