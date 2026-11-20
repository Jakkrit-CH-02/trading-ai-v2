import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest
from pydantic import SecretStr, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api import backtests as bt_api
from app.api.services import Services
from app.auth.core import make_token
from app.auth.crypto import generate_master_key
from app.auth.routes import create_user
from app.backtest.jobs import BacktestRequest, execute
from app.core.config import Settings
from app.core.db import make_session_factory
from app.core.models import Backtest
from app.main import create_app
from app.marketdata.store import InMemoryCandleStore
from app.strategies.base import MarketFrames
from tests import synth
from tests.conftest import needs_pg
from tests.test_api import FakeMarket


def long_market() -> dict[str, MarketFrames]:
    """~2.5 years of 1h bars: enough for one 12m-train / 3m-test walk-forward fold or more."""
    segs = [("up", 1500), ("range", 1500), ("down", 1200), ("up", 1800), ("squeeze", 600)] * 2
    df = synth.make_1h(segs, seed=3)
    df["quote_volume"] *= 1e4  # clear the 24h liquidity filter (real BTC volumes are huge)
    return {"BTCUSDT": synth.frames(df)}


def test_request_validation() -> None:
    with pytest.raises(ValidationError):
        BacktestRequest(strategy="s9", symbols=["BTCUSDT"])
    with pytest.raises(ValidationError):
        BacktestRequest(strategy="s1", symbols=["BTCUSDT", "ETHUSDT"], walk_forward=False)
    with pytest.raises(ValidationError):
        BacktestRequest(strategy="s1", symbols=["BTCUSDT"], years=10)
    assert BacktestRequest(strategy="s1", symbols=["BTCUSDT"]).walk_forward


def test_walk_forward_result_is_json_serialisable_and_complete() -> None:
    req = BacktestRequest(strategy="s1", symbols=["BTCUSDT"], years=3)
    out = execute(long_market(), req)
    json.dumps(out)  # the UI and the JSONB column must be able to hold it
    assert out["walk_forward"] is True and out["folds"]
    f = out["folds"][0]
    assert {"symbol", "test_start", "test_end", "params", "is_pf", "oos_pf", "oos_trades"} <= set(f)
    assert out["metrics"]["n_trades"] >= 0 and "sharpe" in out["metrics"]
    assert out["equity"] and out["buy_hold"] and all(len(p) == 2 for p in out["equity"])
    assert len(out["equity"]) <= 300
    assert out["gate1"]["passed"] is False  # 100 trades are needed; synthetic data cannot give that
    assert out["gate1"]["failures"]


def test_a_single_in_sample_run_can_never_pass_gate1() -> None:
    req = BacktestRequest(strategy="s1", symbols=["BTCUSDT"], walk_forward=False)
    out = execute(long_market(), req)
    assert out["walk_forward"] is False
    assert out["gate1"]["passed"] is False
    assert out["gate1"]["failures"][0] == "not a walk-forward run"
    assert any("NOT out-of-sample" in w for w in out["warnings"])


def test_params_are_applied_and_bad_ones_fail_early() -> None:
    ok = execute(
        long_market(), BacktestRequest(strategy="s1", symbols=["BTCUSDT"], params={"tp1_r": 2.5})
    )
    assert {f["params"].get("tp1_r") for f in ok["folds"]} == {2.5}
    with pytest.raises(ValueError, match="unknown parameters"):
        execute(
            long_market(), BacktestRequest(strategy="s1", symbols=["BTCUSDT"], params={"nope": 1})
        )


def test_not_enough_data_is_reported_not_crashed() -> None:
    short = {"BTCUSDT": synth.frames(synth.standard_market())}
    with pytest.raises(ValueError, match="enough data"):
        execute(short, BacktestRequest(strategy="s1", symbols=["BTCUSDT"]))


# ---- through the API (real database) ---------------------------------------------------------


@pytest.fixture
async def api(
    pg_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[tuple[httpx.AsyncClient, Services]]:
    async def fake_load(store: Any, symbols: list[str], years: float) -> dict[str, MarketFrames]:
        return long_market()

    monkeypatch.setattr(bt_api, "load_frames", fake_load)
    svc = Services(
        settings=Settings(
            _env_file=None,
            jwt_secret=SecretStr("j" * 40),
            master_key=SecretStr(generate_master_key()),
            symbols=["BTCUSDT"],
        ),
        candles=InMemoryCandleStore(),
        market=FakeMarket(),
        db=make_session_factory(pg_engine),
    )
    user, _ = await create_user(svc, "t@example.com", "pw-pw-pw-pw-pw")
    token = make_token("j" * 40, user.id, user.email, "access")
    transport = httpx.ASGITransport(app=create_app(svc))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as c:
        yield c, svc


async def wait_done(c: httpx.AsyncClient, job_id: str) -> dict[str, Any]:
    for _ in range(300):
        j: dict[str, Any] = (await c.get(f"/api/v1/backtests/{job_id}")).json()
        if j["status"] in ("DONE", "FAILED"):
            return j
        await asyncio.sleep(0.1)
    raise AssertionError("backtest did not finish")


@needs_pg
async def test_job_is_queued_runs_and_stores_its_result(
    api: tuple[httpx.AsyncClient, Services],
) -> None:
    c, svc = api
    r = await c.post("/api/v1/backtests", json={"strategy": "s1", "symbols": ["BTCUSDT"]})
    assert r.status_code == 202 and r.json()["status"] == "PENDING" and r.json()["result"] is None
    job = await wait_done(c, r.json()["id"])
    assert job["status"] == "DONE" and job["error"] is None
    assert job["result"]["folds"] and job["result"]["gate1"]["passed"] is False
    listed = (await c.get("/api/v1/backtests")).json()
    assert listed[0]["id"] == job["id"] and listed[0]["result"] is None  # list stays light
    assert svc.db
    async with svc.db() as s:
        row = (await s.execute(select(Backtest))).scalar_one()
    assert row.metrics is not None
    assert row.metrics["walk_forward"] is True and row.status == "DONE"


@needs_pg
async def test_failures_are_recorded_and_bad_requests_rejected(
    api: tuple[httpx.AsyncClient, Services], monkeypatch: pytest.MonkeyPatch
) -> None:
    c, _ = api

    async def boom(store: Any, symbols: list[str], years: float) -> Any:
        raise ValueError("no 1h candles for BTCUSDT; run `softtrade backfill` first")

    monkeypatch.setattr(bt_api, "load_frames", boom)
    r = await c.post("/api/v1/backtests", json={"strategy": "s2", "symbols": ["BTCUSDT"]})
    job = await wait_done(c, r.json()["id"])
    assert job["status"] == "FAILED" and "backfill" in job["error"]
    assert (
        await c.post("/api/v1/backtests", json={"strategy": "s1", "symbols": ["DOGEUSDT"]})
    ).status_code == 422
    assert (
        await c.post(
            "/api/v1/backtests",
            json={"strategy": "s1", "symbols": ["BTCUSDT"], "params": {"zzz": 1}},
        )
    ).status_code == 422
    assert (
        await c.get("/api/v1/backtests/00000000-0000-0000-0000-000000000000")
    ).status_code == 404
    anon = httpx.AsyncClient(transport=c._transport, base_url="http://test")
    assert (await anon.get("/api/v1/backtests")).status_code == 401


@needs_pg
async def test_jobs_left_running_by_a_dead_process_are_failed_on_startup(
    api: tuple[httpx.AsyncClient, Services],
) -> None:
    _, svc = api
    assert svc.db
    async with svc.db() as s:
        s.add(Backtest(strategy_config_snapshot={}, range={}, fees_model={}, status="RUNNING"))
        await s.commit()
    await bt_api.fail_interrupted(svc)
    async with svc.db() as s:
        row = (await s.execute(select(Backtest))).scalar_one()
    assert row.metrics is not None
    assert row.status == "FAILED" and "restart" in row.metrics["error"]
