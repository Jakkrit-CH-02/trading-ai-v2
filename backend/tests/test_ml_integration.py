"""S_ml inside the real decision path: backtest hook, live == backtest, runner and API."""

from datetime import datetime, timedelta
from functools import partial
from typing import Any

import numpy as np
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.backtest.engine import BacktestConfig, run_backtest
from app.core.db import make_session_factory
from app.core.models import AuditLog, Decision
from app.core.models import Signal as SignalRow
from app.ml import registry
from app.ml.evaluate import Comparison, compare_backtests, prepare_symbols, verdict
from app.ml.features import FEATURE_NAMES, with_ml_features
from app.ml.scorer import NEUTRAL, MlScorer, ScorerPool
from app.ml.train import fit
from app.runtime.frames import WINDOW_BARS, load_features
from app.runtime.runner import BotRunner
from app.strategies.base import MarketFrames
from app.strategies.decision import decide_at_close
from app.strategies.s1_trend import S1Trend
from tests.conftest import needs_pg
from tests.ml_synth import synth_dataset
from tests.synth import standard_market, to_4h
from tests.test_bots_api import CODE, Env, env  # noqa: F401  (fixture)
from tests.test_ml_registry import add_model, candidate, tiny_booster
from tests.test_runner import CFG, load_market, make_bot
from tests.test_runner import Env as RunnerEnv
from tests.test_runtime_parity import long_market, store_with

NO_VOLUME_FILTER = BacktestConfig(min_quote_volume_24h=0.0)


def prepared_market() -> Any:
    df = standard_market()
    return prepare_symbols(
        "s1", {"BTCUSDT": MarketFrames("BTCUSDT", {"1h": df, "4h": to_4h(df)}, None)}
    )


# ---- the hook in the engine ----


def test_a_neutral_ml_score_changes_nothing_and_the_extremes_move_the_decisions() -> None:
    (p,) = prepared_market()
    base = run_backtest(p.strategy, p.feats, NO_VOLUME_FILTER)
    same = run_backtest(p.strategy, p.feats, NO_VOLUME_FILTER, ml_score=lambda f, i, s: NEUTRAL)
    assert [(t.entry_time, t.pnl) for t in same.trades] == [
        (t.entry_time, t.pnl) for t in base.trades
    ]
    assert base.trades  # the market produces trades, so the comparisons below mean something
    veto = run_backtest(p.strategy, p.feats, NO_VOLUME_FILTER, ml_score=lambda f, i, s: 0.0)
    assert veto.trades == [] and all(r.decision != Decision.TAKEN for r in veto.signals)
    keen = run_backtest(p.strategy, p.feats, NO_VOLUME_FILTER, ml_score=lambda f, i, s: 100.0)
    assert len(keen.trades) >= len(base.trades)
    assert {r.score.s_ml for r in veto.signals} == {0.0} and {
        r.score.s_ai for r in veto.signals
    } == {50.0}


def fixed(value: float, _sig: Any) -> float:
    return value


def test_decide_at_close_records_the_s_ml_it_was_given() -> None:
    (p,) = prepared_market()
    cfg = NO_VOLUME_FILTER
    i = next(i for i in range(len(p.feats)) if p.strategy.evaluate(p.feats, i) is not None)
    for want in (10.0, 50.0, 90.0):
        bd = decide_at_close(p.strategy, p.feats, i, cfg.weights, 0.0, False, partial(fixed, want))
        assert bd is not None and bd.score.s_ml == want
    default = decide_at_close(p.strategy, p.feats, i, cfg.weights, 0.0, False)
    assert default is not None and default.score.s_ml == 50.0


def test_the_comparison_uses_out_of_fold_scores_and_a_small_gain_does_not_count() -> None:
    import pandas as pd

    prepared = prepared_market()
    (p,) = prepared
    times = [p.feats.index[i] for i in range(len(p.feats)) if p.strategy.evaluate(p.feats, i)]
    oof = pd.DataFrame({"symbol": "BTCUSDT", "t": times, "y": 0, "p": 0.99})  # "always great"
    cmp = compare_backtests(prepared, oof, 0.3, NO_VOLUME_FILTER)
    assert isinstance(cmp, Comparison) and cmp.n_symbols == 1 and cmp.period[0] == min(times)
    assert cmp.with_ml.n_trades >= cmp.baseline.n_trades
    ok, why = verdict(cmp)
    assert isinstance(ok, bool) and "trades" in why


def test_verdict_needs_enough_trades_and_a_real_improvement() -> None:
    from app.backtest.metrics import Metrics

    def m(n: int, exp: float, pnl: float) -> Metrics:
        return Metrics(n, 0.4, 1.0, exp, pnl, 0.0, 0.01, 0.0, 0.0)

    def c(b: Metrics, w: Metrics) -> Comparison:
        return Comparison(b, w, 0, (np.datetime64("2024-01-01"), np.datetime64("2025-01-01")), 1)  # type: ignore[arg-type]

    assert not verdict(c(m(30, -0.1, -5), m(30, 0.3, 20)))[0]  # too few trades
    assert not verdict(c(m(100, -0.09, -10), m(95, -0.06, -4)))[0]  # +0.03R is noise
    assert not verdict(c(m(100, 0.0, 0), m(95, 0.2, -1)))[0]  # better R but worse money
    assert verdict(c(m(100, -0.09, -10), m(90, 0.02, 5)))[0]


# ---- live == backtest (SPEC principle 2) ----


def trained_scorer() -> MlScorer:
    df = synth_dataset(500)
    b = fit(df[FEATURE_NAMES].to_numpy(), df["y"].to_numpy(), {"num_leaves": 5}, 30, 1)
    return MlScorer(b, 0.3, 1)


async def test_the_live_path_scores_every_signal_exactly_like_the_backtest() -> None:
    df = long_market()
    data = MarketFrames("BTCUSDT", {"1h": df, "4h": to_4h(df)}, None)
    strat = S1Trend()
    full = with_ml_features(strat.prepare(data), data)
    store = await store_with(df, "BTCUSDT", None)
    scorer = trained_scorer()
    start = WINDOW_BARS["1h"]  # only bars beyond the live window test the window
    bars = [i for i in range(start, len(full)) if strat.evaluate(full, i) is not None]
    assert len(bars) >= 8, "the synthetic market must fire signals beyond the window"
    for i in bars[:: max(1, len(bars) // 12)]:
        live = await load_features(store, strat, "BTCUSDT", full.time(i), with_ml=True)
        j = len(live) - 1
        sig_full, sig_live = strat.evaluate(full, i), strat.evaluate(live, j)
        assert sig_full is not None and sig_live is not None
        a, b = scorer.s_ml(full, i, sig_full), scorer.s_ml(live, j, sig_live)
        assert a == pytest.approx(b, abs=1e-6), f"bar {full.time(i)}"
        assert a != NEUTRAL  # the model has an opinion, so the check is not vacuous


# ---- the runner ----


def runner_at(env_: Any, bar: datetime, sessions: Any) -> BotRunner:
    return BotRunner(
        sessions, env_.candles, CFG, wait_for_htf_s=0.0,
        now=lambda: bar + timedelta(hours=1, seconds=10), scorers=ScorerPool(sessions),
    )  # fmt: skip


@needs_pg
async def test_the_runner_scores_with_the_active_model_and_records_s_ml(
    pg_engine: AsyncEngine,
) -> None:
    sessions = make_session_factory(pg_engine)
    env_ = RunnerEnv(sessions)
    await make_bot(sessions)
    feats, i = await load_market(env_)
    bar = feats.time(i)
    cand, hold = candidate()
    row, promoted, _ = await registry.save_candidate(sessions, "S1", cand, hold)
    assert promoted and row.status == "active"
    scorer = await ScorerPool(sessions).get("s1", 0.0)
    assert scorer is not None

    out = await runner_at(env_, bar, sessions).on_candle_closed("BTCUSDT", "1h", bar)
    assert len(out) == 1
    live = await load_features(env_.candles, S1Trend(), "BTCUSDT", bar, with_ml=True)
    want = scorer.s_ml(live, len(live) - 1, out[0].decision.signal)
    assert want != NEUTRAL  # the model has an opinion, so this is not a vacuous check
    assert out[0].decision.score.s_ml == pytest.approx(want, abs=1e-6)
    async with sessions() as db:
        stored = (await db.execute(select(SignalRow.s_ml))).scalar_one()
    assert stored is not None and float(stored) == pytest.approx(want, abs=1e-6)


@needs_pg
async def test_a_suspended_model_leaves_s_ml_neutral(pg_engine: AsyncEngine) -> None:
    sessions = make_session_factory(pg_engine)
    env_ = RunnerEnv(sessions)
    await make_bot(sessions)
    feats, i = await load_market(env_)
    await add_model(sessions, "S1", 1, "suspended", tiny_booster().model_to_string())
    bar = feats.time(i)
    out = await runner_at(env_, bar, sessions).on_candle_closed("BTCUSDT", "1h", bar)
    assert out[0].decision.score.s_ml == NEUTRAL


# ---- API ----


@needs_pg
async def test_models_are_listed_with_their_evidence_and_rollback_needs_2fa(env: Env) -> None:  # noqa: F811
    assert env.svc.db
    await add_model(env.svc.db, "S1", 1, "retired")
    await add_model(env.svc.db, "S1", 2, "active")
    j = (await env.c.get("/api/v1/ml/models")).json()
    assert [(m["strategy"], m["version"], m["status"]) for m in j] == [
        ("S1", 2, "active"),
        ("S1", 1, "retired"),
    ]
    assert (await env.c.post("/api/v1/ml/S1/rollback")).status_code == 401  # no X-TOTP
    assert (await env.c.post("/api/v1/ml/S9/rollback", headers=CODE)).status_code == 404
    assert (
        await env.c.post("/api/v1/ml/S2/rollback", headers=CODE)
    ).status_code == 409  # nothing earlier
    r = await env.c.post("/api/v1/ml/s1/rollback", headers=CODE)
    assert r.status_code == 200 and r.json()["version"] == 1 and r.json()["status"] == "active"
    async with env.svc.db() as db:
        assert "ml.rollback" in list((await db.execute(select(AuditLog.action))).scalars())
    after = (await env.c.get("/api/v1/ml/models")).json()
    assert {m["version"]: m["status"] for m in after} == {1: "active", 2: "retired"}
