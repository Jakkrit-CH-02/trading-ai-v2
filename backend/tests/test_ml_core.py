"""Features, labels, purged validation, metrics and the promotion rule (no database)."""

import math
from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.core.models import Side
from app.ml import registry
from app.ml.features import BASE_FEATURES, FEATURE_NAMES, PREFIX, feature_frame, with_ml_features
from app.ml.labels import DEFAULT_HORIZON, build_dataset, label_signal
from app.ml.metrics import auc, logloss, metrics
from app.ml.scorer import NEUTRAL, p_to_score
from app.ml.train import TrainConfig, bin_shares, psi, purged_splits, train_candidate
from app.strategies.base import MarketFrames
from app.strategies.features import Features
from app.strategies.s1_trend import S1Trend
from app.strategies.types import Signal
from tests.ml_synth import synth_dataset
from tests.synth import standard_market, to_4h

# ---- features: causal, no look-ahead ----


def frames_until(df: pd.DataFrame, k: int) -> MarketFrames:
    cut = df.iloc[:k]
    return MarketFrames("BTCUSDT", {"1h": cut, "4h": to_4h(cut)}, None)


def test_every_ml_feature_at_bar_t_ignores_the_future() -> None:
    df = standard_market()
    k = next(i for i in range(4000, 4100) if df.index[i].hour % 4 == 0)  # a closed 4h boundary
    full = feature_frame(frames_until(df, len(df)))
    part = feature_frame(frames_until(df, k))
    assert list(full.columns) == BASE_FEATURES
    got, want = part.iloc[-300:], full.loc[part.index[-300:]]
    pd.testing.assert_frame_equal(got, want, check_exact=False, rtol=1e-9, atol=1e-12)


def test_ml_columns_are_added_next_to_the_strategy_features() -> None:
    df = standard_market().iloc[:3000]
    data = frames_until(df, len(df))
    base = S1Trend().prepare(data)
    f = with_ml_features(base, data)
    assert set(base.cols) < set(f.cols) and all(PREFIX + n in f.cols for n in BASE_FEATURES)
    assert len(f.cols[PREFIX + "rsi14"]) == len(base)


# ---- triple-barrier labels ----


def fx(open_: list[float], high: list[float], low: list[float]) -> Features:
    n = len(open_)
    idx = pd.date_range("2024-01-01", periods=n, freq="1h", tz="UTC")
    return Features(
        "BTCUSDT",
        "1h",
        idx,
        {"open": np.array(open_), "high": np.array(high), "low": np.array(low)},
    )


def sig(stop: str = "95", tp: str | None = "110", bars: int | None = None) -> Signal:
    tp1 = None if tp is None else Decimal(tp)
    return Signal(
        "s1", "BTCUSDT", Side.BUY, datetime(2024, 1, 1, tzinfo=UTC), Decimal(100), Decimal(stop),
        70.0, tp1=tp1, time_stop_bars=bars,
    )  # fmt: skip


def test_the_target_before_the_stop_is_a_win() -> None:
    f = fx([100, 100, 105, 108], [100, 104, 112, 109], [100, 99, 104, 107])
    lab = label_signal(f, 0, sig())
    assert (lab.y, lab.end_idx) == (1, 2)  # type: ignore[union-attr]


def test_the_stop_before_the_target_is_a_loss() -> None:
    f = fx([100, 100, 96, 100], [100, 101, 97, 120], [100, 99, 94, 99])
    lab = label_signal(f, 0, sig())
    assert (lab.y, lab.end_idx) == (0, 2)  # type: ignore[union-attr]


def test_a_bar_touching_both_barriers_counts_as_the_stop() -> None:
    f = fx([100, 100, 100], [100, 112, 100], [100, 94, 100])
    assert label_signal(f, 0, sig()).y == 0  # type: ignore[union-attr]


def test_a_gap_open_below_the_stop_is_a_loss_at_once() -> None:
    f = fx([100, 90, 120], [100, 130, 130], [100, 89, 100])
    lab = label_signal(f, 0, sig())
    assert (lab.y, lab.end_idx) == (0, 1)  # type: ignore[union-attr]


def test_neither_barrier_within_the_horizon_is_not_a_win_and_unresolved_is_unknown() -> None:
    quiet = [100.0] * 10
    f = fx(quiet, [101.0] * 10, [99.0] * 10)
    lab = label_signal(f, 0, sig(bars=3))
    assert (lab.y, lab.end_idx) == (0, 3)  # type: ignore[union-attr]
    assert label_signal(f, 8, sig(bars=3)) is None  # the horizon runs past the data
    assert label_signal(f, 9, sig()) is None and label_signal(f, 0, sig(tp=None)) is None
    assert DEFAULT_HORIZON == 48


def test_the_dataset_has_one_row_per_resolved_signal_with_known_inputs() -> None:
    df = standard_market().iloc[:5000]
    data = frames_until(df, len(df))
    strat = S1Trend()
    feats = with_ml_features(strat.prepare(data), data)
    ds = build_dataset(strat.evaluate, feats, "BTCUSDT")
    assert len(ds) > 10 and set(ds["y"]) <= {0, 1}
    assert (ds["t_end"] >= ds["t"]).all() and ds[["s_tech", "risk_pct", "rr"]].notna().all().all()
    assert list(ds.columns)[:4] == ["symbol", "t", "t_end", "y"] and set(FEATURE_NAMES) <= set(
        ds.columns
    )


# ---- purged walk-forward ----


def test_training_never_sees_a_sample_whose_outcome_overlaps_the_test_period() -> None:
    df = synth_dataset(600, hold_h=48)
    cfg = TrainConfig()
    splits = purged_splits(df, cfg.n_folds, cfg.min_train_frac, cfg.embargo)
    assert len(splits) == cfg.n_folds
    for tr, te in splits:
        t0 = df["t"].iloc[te[0]]
        assert (df["t_end"].iloc[tr] < t0 - cfg.embargo).all()  # purged + embargo
        assert tr.max() < te.min() and len(tr) > 0  # only the past
    firsts = [te[0] for _, te in splits]
    assert firsts == sorted(firsts) and splits[0][1][0] >= int(0.4 * len(df))


def test_purging_removes_exactly_the_samples_that_would_leak() -> None:
    """Negative control: with outcomes that resolve at once nothing needs purging; with long
    outcome windows the samples just before each test block are dropped."""
    n, cfg = 400, TrainConfig(embargo_hours=0)
    instant = synth_dataset(n, hold_h=0)
    long_ = synth_dataset(n, hold_h=30)  # each outcome depends on the next 30 h = 10 samples
    for (tr_a, te_a), (tr_b, te_b) in zip(
        purged_splits(instant, cfg.n_folds, cfg.min_train_frac, cfg.embargo),
        purged_splits(long_, cfg.n_folds, cfg.min_train_frac, cfg.embargo),
        strict=True,
    ):
        assert len(tr_a) == te_a[0]  # everything earlier is usable
        assert len(tr_b) == te_b[0] - 10  # ... minus the 10 samples whose outcome reaches the test
        assert (long_["t_end"].iloc[tr_b] < long_["t"].iloc[te_b[0]]).all()


def test_metrics_match_hand_computed_values() -> None:
    y = np.array([0, 0, 1, 1])
    assert auc(y, np.array([0.1, 0.2, 0.8, 0.9])) == 1.0
    assert auc(y, np.array([0.9, 0.8, 0.2, 0.1])) == 0.0
    assert auc(y, np.full(4, 0.5)) == 0.5  # ties
    assert math.isnan(auc(np.ones(4, dtype=int), np.arange(4.0)))
    assert logloss(np.array([1]), np.array([0.5])) == pytest.approx(math.log(2))
    m = metrics(y, np.array([0.1, 0.2, 0.8, 0.9]))
    assert m["base_rate"] == 0.5 and m["precision_top30"] == 1.0 and m["n"] == 4


def test_a_model_finds_a_real_signal_and_not_noise() -> None:
    cfg = TrainConfig(optuna_trials=3, n_folds=3)
    real = train_candidate(synth_dataset(700, informative=True), cfg)
    assert real.holdout["auc"] > 0.62 and real.cv["auc"] > 0.62 and real.n_samples == 700
    assert 0 < real.base_rate < 1 and set(real.psi_ref) == set(BASE_FEATURES)
    noise = train_candidate(synth_dataset(700, informative=False), cfg)
    assert noise.holdout["auc"] < 0.62  # nothing to learn
    with pytest.raises(ValueError, match="not enough"):
        train_candidate(synth_dataset(50), cfg)
    one_class = synth_dataset(300).assign(y=0)
    with pytest.raises(ValueError):
        train_candidate(one_class, cfg)


# ---- drift, scoring, promotion ----


def test_psi_is_zero_for_the_same_data_and_large_for_a_shift() -> None:
    rng = np.random.default_rng(0)
    a = rng.normal(size=5000)
    edges = np.quantile(a, np.linspace(0.1, 0.9, 9))
    ref = bin_shares(a, edges)
    assert ref.sum() == pytest.approx(1.0) and len(ref) == 11  # 10 bins + the NaN bin
    assert psi(ref, bin_shares(rng.normal(size=5000), edges)) < 0.05
    assert psi(ref, bin_shares(rng.normal(loc=1.5, size=5000), edges)) > 0.25
    withnan = np.append(a, [np.nan] * 500)
    assert bin_shares(withnan, edges)[-1] == pytest.approx(500 / 5500)


def test_s_ml_is_centred_on_the_base_rate_and_always_within_0_100() -> None:
    assert p_to_score(0.3, 0.3) == NEUTRAL
    assert p_to_score(0.5, 0.3) == pytest.approx(70.0) and p_to_score(0.1, 0.3) == pytest.approx(
        30.0
    )
    assert p_to_score(0.99, 0.1) == 100.0 and p_to_score(0.0, 0.9) == 0.0
    assert p_to_score(float("nan"), 0.3) == NEUTRAL and p_to_score(0.4, float("nan")) == NEUTRAL


def good(**o: float) -> dict[str, float]:
    return {"n": 100, "auc": 0.65, "logloss": 0.55, "base_logloss": 0.62, **o}


def test_a_model_is_promoted_only_when_it_clearly_beats_chance_and_the_champion() -> None:
    assert registry.promotion_decision(good(), None)[0]
    assert not registry.promotion_decision(good(n=10), None)[0]
    assert not registry.promotion_decision(good(auc=0.52), None)[0]
    assert not registry.promotion_decision(good(logloss=0.7), None)[0]  # worse than the base rate
    assert not registry.promotion_decision({**good(), "auc": float("nan")}, None)[0]
    champ = good(auc=0.60, logloss=0.58)
    assert registry.promotion_decision(good(), champ)[0]
    assert not registry.promotion_decision(good(auc=0.59), champ)[0]
    assert not registry.promotion_decision(good(logloss=0.59), champ)[0]
    assert datetime.now(UTC)  # (keeps the datetime import honest)
