"""Model registry, scorer pool and monitoring against a real database."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import lightgbm as lgb
import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.db import make_session_factory
from app.core.models import MlModel, MlModelStatus
from app.marketdata.store import InMemoryCandleStore
from app.ml import pipeline as pipeline_mod
from app.ml import registry
from app.ml.features import FEATURE_NAMES
from app.ml.pipeline import drift, monitor_model, precision_check
from app.ml.scorer import NEUTRAL, MlScorer, ScorerPool, scorer_from_row
from app.ml.train import Candidate, TrainConfig, train_candidate
from tests.conftest import needs_pg
from tests.ml_synth import synth_dataset
from tests.synth import make_1h, to_4h
from tests.test_runtime_parity import klines

pytestmark = needs_pg
CFG = TrainConfig(optuna_trials=2, n_folds=3)


def candidate(df: pd.DataFrame | None = None) -> tuple[Candidate, pd.DataFrame]:
    df = (df if df is not None else synth_dataset(600)).sort_values("t").reset_index(drop=True)
    return train_candidate(df, CFG), df.iloc[int(len(df) * 0.8) :]


async def add_model(
    sessions: async_sessionmaker[AsyncSession], strategy: str, version: int, status: str,
    text: str = "x",
) -> uuid.UUID:  # fmt: skip
    async with sessions.begin() as db:
        m = MlModel(
            strategy=strategy, version=version, status=status, trained_from=datetime.now(UTC),
            trained_to=datetime.now(UTC), n_samples=10, metrics={}, params={}, psi_ref={},
            model_text=text,
        )  # fmt: skip
        db.add(m)
        await db.flush()
        return m.id


async def statuses(sessions: async_sessionmaker[AsyncSession], strategy: str) -> dict[int, str]:
    async with sessions() as db:
        rows = (await db.execute(select(MlModel).where(MlModel.strategy == strategy))).scalars()
        return {m.version: m.status for m in rows}


# ---- promote / keep ----


async def test_a_good_first_model_is_promoted_and_a_clone_does_not_replace_it(
    pg_engine: AsyncEngine,
) -> None:
    sessions = make_session_factory(pg_engine)
    cand, hold = candidate()
    row, ok, reason = await registry.save_candidate(sessions, "S1", cand, hold)
    assert ok and row.version == 1 and row.status == MlModelStatus.ACTIVE and "AUC" in reason
    assert row.metrics["train"]["base_rate"] == pytest.approx(cand.base_rate)
    again, ok2, why = await registry.save_candidate(sessions, "S1", cand, hold)
    assert not ok2 and again.version == 2 and "does not beat the active model" in why
    assert await statuses(sessions, "S1") == {1: "active", 2: "candidate"}


async def test_a_failed_backtest_blocks_promotion_even_with_good_statistics(
    pg_engine: AsyncEngine,
) -> None:
    sessions = make_session_factory(pg_engine)
    cand, hold = candidate()
    bt: tuple[bool, str, dict[str, Any]] = (False, "expectancy -0.09R -> -0.06R", {})
    row, ok, reason = await registry.save_candidate(sessions, "S1", cand, hold, backtest=bt)
    assert not ok and row.status == MlModelStatus.CANDIDATE and "backtest" in reason
    assert row.metrics["backtest"]["improves"] is False


async def test_a_model_with_no_edge_is_kept_as_a_candidate_only(pg_engine: AsyncEngine) -> None:
    sessions = make_session_factory(pg_engine)
    cand, hold = candidate(synth_dataset(600, informative=False))
    row, ok, _ = await registry.save_candidate(sessions, "S2", cand, hold)
    assert not ok and row.status == MlModelStatus.CANDIDATE


async def test_rollback_reactivates_the_previous_version_and_suspend_switches_off(
    pg_engine: AsyncEngine,
) -> None:
    sessions = make_session_factory(pg_engine)
    assert await registry.rollback(sessions, "S1") is None  # nothing to go back to
    await add_model(sessions, "S1", 1, "retired")
    v2 = await add_model(sessions, "S1", 2, "active")
    m = await registry.rollback(sessions, "S1")
    assert m is not None and m.version == 1
    assert await statuses(sessions, "S1") == {1: "active", 2: "retired"}
    await registry.suspend(sessions, v2, "ignored: not active")
    assert (await statuses(sessions, "S1"))[2] == "retired"
    async with sessions() as db:
        v1 = (await db.execute(select(MlModel.id).where(MlModel.version == 1))).scalar_one()
    await registry.suspend(sessions, v1, "feature drift: " + "x" * 600)
    async with sessions() as db:
        row = (await db.execute(select(MlModel).where(MlModel.version == 1))).scalar_one()
    assert row.status == "suspended" and row.note is not None and len(row.note) == 500


# ---- scorer ----


def tiny_booster(seed: int = 0) -> lgb.Booster:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=(300, len(FEATURE_NAMES)))
    y = (x[:, 0] > 0).astype(int)
    ds = lgb.Dataset(x, label=y, feature_name=FEATURE_NAMES)
    return lgb.train({"objective": "binary", "verbosity": -1, "num_leaves": 4}, ds, 20)


async def test_the_pool_serves_only_the_active_model_and_caches_for_a_while(
    pg_engine: AsyncEngine,
) -> None:
    sessions = make_session_factory(pg_engine)
    pool = ScorerPool(sessions, ttl_s=60)
    assert await pool.get("s1", 0.0) is None  # no model: neutral
    cand, hold = candidate()
    row, _, _ = await registry.save_candidate(sessions, "S1", cand, hold)
    assert await pool.get("s1", 10.0) is None  # still cached as "none"
    scorer = await pool.get("s1", 100.0)  # ttl passed
    assert isinstance(scorer, MlScorer) and scorer.version == row.version
    assert scorer.base_rate == pytest.approx(cand.base_rate)
    await registry.suspend(sessions, row.id, "drift")
    assert await pool.get("s1", 120.0) is scorer  # cached
    assert await pool.get("s1", 200.0) is None  # suspended models never score


async def test_a_corrupt_stored_model_means_neutral_not_a_crash(pg_engine: AsyncEngine) -> None:
    sessions = make_session_factory(pg_engine)
    await add_model(sessions, "S1", 1, "active", text="this is not a lightgbm model")
    assert await ScorerPool(sessions).get("s1", 0.0) is None


def test_the_scorer_falls_back_to_neutral_on_anything_unexpected() -> None:
    from tests.test_ml_core import fx, sig

    s = MlScorer(tiny_booster(), 0.3, 1)
    f = fx([100.0, 100.0], [101.0, 101.0], [99.0, 99.0])
    assert s.s_ml(f, 0, sig()) == NEUTRAL  # no ml_* columns in the features
    assert s.s_ml(f, 0, sig(tp=None)) == NEUTRAL  # no target
    s.booster = None  # type: ignore[assignment]
    assert s.s_ml(f, 0, sig()) == NEUTRAL
    row = MlModel(version=3, metrics={}, model_text=tiny_booster().model_to_string())
    assert scorer_from_row(row).version == 3  # a model without a base rate loads (scores neutral)
    assert scorer_from_row(row).base_rate != scorer_from_row(row).base_rate  # NaN


# ---- monitoring ----


def test_drift_and_precision_checks() -> None:
    from app.ml.features import BASE_FEATURES

    rng = np.random.default_rng(0)
    base = pd.DataFrame(rng.normal(size=(3000, len(BASE_FEATURES))), columns=BASE_FEATURES)
    from app.ml.train import psi_reference

    ref = psi_reference(base)
    same = drift(
        ref, pd.DataFrame(rng.normal(size=(2000, len(BASE_FEATURES))), columns=BASE_FEATURES)
    )
    assert max(same.values()) < 0.1
    shifted = drift(ref, base + 2.0)
    assert all(v > 0.25 for v in shifted.values()) and set(shifted) == set(BASE_FEATURES)
    y, p = np.array([1] * 5 + [0] * 25), np.full(30, 0.9)
    ok, msg = precision_check(y, p, 0.3)
    assert not ok and "0.17" in msg  # liked signals win less often than the base rate
    assert precision_check(np.ones(30), p, 0.3)[0]
    assert precision_check(y[:10], p[:10], 0.3)[0]  # too few liked signals to judge


async def market_store(end: datetime) -> InMemoryCandleStore:
    df = make_1h([("range", 9000)], seed=2)  # stationary: no regime change to look like drift
    last = pd.Timestamp(end).floor("4h") - pd.Timedelta(hours=1)
    df.index = pd.date_range(end=last, periods=len(df), freq="1h", tz="UTC", name=df.index.name)
    st = InMemoryCandleStore()
    for sym in ("BTCUSDT",):
        await st.save(klines(df, sym, "1h") + klines(to_4h(df), sym, "4h"))
    return st


async def test_monitoring_suspends_a_model_whose_inputs_no_longer_look_like_training(
    pg_engine: AsyncEngine,
) -> None:
    sessions = make_session_factory(pg_engine)
    now = datetime.now(UTC)
    store = await market_store(now)
    none = await monitor_model(sessions, store, "s1", ["BTCUSDT"], now)
    assert none.version is None and not none.suspended
    cand, hold = candidate()  # trained on random normal features: nothing like real candles
    await registry.save_candidate(sessions, "S1", cand, hold)
    r = await monitor_model(sessions, store, "s1", ["BTCUSDT"], now)
    assert (
        r.suspended and len(r.drifted) >= pipeline_mod.PSI_FEATURES and "feature drift" in r.reason
    )
    assert (await statuses(sessions, "S1"))[1] == "suspended"


async def test_a_model_trained_on_these_markets_is_left_running(
    pg_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ml.evaluate import prepare_symbols
    from app.ml.pipeline import load, market_frame

    sessions = make_session_factory(pg_engine)
    now = datetime.now(UTC)
    store = await market_store(now)
    frames = await load(store, ["BTCUSDT"], now - timedelta(days=400), now)
    market = market_frame(prepare_symbols("s1", frames))
    df = synth_dataset(600).sort_values("t").reset_index(drop=True)
    cand = train_candidate(df, CFG, market)  # reference = the real market state
    await registry.save_candidate(sessions, "S1", cand, df.iloc[480:])
    monkeypatch.setattr(pipeline_mod, "precision_check", lambda y, p, b: (True, "ok"))
    r = await monitor_model(sessions, store, "s1", ["BTCUSDT"], now)
    assert not r.suspended and len(r.drifted) < pipeline_mod.PSI_FEATURES
    assert (await statuses(sessions, "S1"))[1] == "active"


async def test_a_losing_filter_is_switched_off_even_without_drift(
    pg_engine: AsyncEngine, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.ml.evaluate import prepare_symbols
    from app.ml.pipeline import load, market_frame

    sessions = make_session_factory(pg_engine)
    now = datetime.now(UTC)
    store = await market_store(now)
    frames = await load(store, ["BTCUSDT"], now - timedelta(days=400), now)
    df = synth_dataset(600).sort_values("t").reset_index(drop=True)
    cand = train_candidate(df, CFG, market_frame(prepare_symbols("s1", frames)))
    await registry.save_candidate(sessions, "S1", cand, df.iloc[480:])
    # give the monitor recent resolved signals to judge, and a precision check that fails
    recent = df.iloc[:40].assign(t=pd.Timestamp(now - timedelta(days=5)))
    monkeypatch.setattr(pipeline_mod, "build_all", lambda prepared: recent)
    monkeypatch.setattr(
        pipeline_mod, "precision_check", lambda y, p, b: (False, "precision 0.10 vs 0.30")
    )
    r = await monitor_model(sessions, store, "s1", ["BTCUSDT"], now)
    assert r.suspended and "precision" in r.reason and "feature drift" not in r.reason
    assert (await statuses(sessions, "S1"))[1] == "suspended"


async def test_retraining_is_due_only_for_a_missing_or_week_old_model(
    pg_engine: AsyncEngine,
) -> None:
    from app.ml.pipeline import retrain_due

    sessions = make_session_factory(pg_engine)
    now, week = datetime.now(UTC), timedelta(days=7)
    assert await retrain_due(sessions, "s1", now, week)  # never trained
    await add_model(sessions, "S1", 1, "candidate")
    assert not await retrain_due(sessions, "s1", now, week)  # a restart must not retrain
    assert await retrain_due(sessions, "s1", now + timedelta(days=8), week)
    assert await retrain_due(sessions, "s2", now, week)  # per strategy
