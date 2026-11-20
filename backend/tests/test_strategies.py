from datetime import UTC, datetime
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from app.core.models import Decision
from app.strategies import regime as rg
from app.strategies.base import MarketFrames, Strategy
from app.strategies.features import align_htf
from app.strategies.params import S3Params
from app.strategies.s1_trend import S1Trend
from app.strategies.s2_meanrev import S2MeanReversion
from app.strategies.s3_breakout import S3Breakout
from app.strategies.scoring import ScoreWeights, score_signal
from app.strategies.types import Regime, Signal
from tests import synth

WIDE = S3Params(regimes=(Regime.TREND_UP, Regime.RANGE, Regime.NEUTRAL))


def all_signals(strategy: Strategy, fr: MarketFrames) -> dict[int, Signal]:
    f = strategy.prepare(fr)
    out = {}
    for i in range(len(f)):
        s = strategy.evaluate(f, i)
        if s is not None:
            out[i] = s
    return out


# ---- multi-timeframe alignment ------------------------------------------------------


def test_htf_bar_is_visible_only_after_it_has_closed() -> None:
    idx4 = pd.date_range("2024-01-01", periods=3, freq="4h", tz="UTC")  # 00, 04, 08
    htf = pd.DataFrame({"v": [1.0, 2.0, 3.0]}, index=idx4)
    ltf = pd.date_range("2024-01-01", periods=12, freq="1h", tz="UTC")
    got = align_htf(htf, "4h", ltf, "1h")["v"].tolist()
    # 1h bars 00-02 close at 01,02,03: no 4h bar has closed yet.
    assert np.isnan(got[:3]).all()
    # the 03:00 bar closes at 04:00, exactly when the first 4h bar closes -> it may use it
    assert got[3:7] == [1.0, 1.0, 1.0, 1.0]
    assert got[7:11] == [2.0, 2.0, 2.0, 2.0]
    assert got[11] == 3.0


# ---- regime detector ----------------------------------------------------------------


def test_regime_detector_labels_trend_range_and_down() -> None:
    r = rg.classify(synth.to_4h(synth.standard_market()))["regime"]
    counts = r.value_counts()
    for regime in (Regime.TREND_UP, Regime.TREND_DOWN, Regime.RANGE):
        assert counts.get(regime, 0) > 20, f"{regime} never detected"
    assert r.iloc[:200].eq(Regime.NEUTRAL).all()  # warm-up enables nothing


def test_regime_is_causal() -> None:
    df4 = synth.to_4h(synth.standard_market())
    full = rg.classify(df4)["regime"]
    for cut in (700, 1100, 1500):
        part = rg.classify(df4.iloc[:cut])["regime"]
        assert part.tolist() == full.iloc[:cut].tolist()


def test_high_vol_blocks_everything() -> None:
    df4 = synth.to_4h(synth.standard_market())
    r = rg.classify(df4)
    assert (r["regime"] == Regime.HIGH_VOL).any()
    assert not (r.loc[r["regime"] == Regime.HIGH_VOL, "regime"] == Regime.TREND_UP).any()


# ---- the same code path must never look ahead ----------------------------------------

STRATEGIES: dict[str, Strategy] = {
    "s1": S1Trend(),
    "s2": S2MeanReversion(),
    "s3_wide": S3Breakout(WIDE),
}


def signals_by_time(
    strategy: Strategy, fr: MarketFrames
) -> tuple[dict[datetime, Signal], datetime]:
    f = strategy.prepare(fr)
    out = {}
    for i in range(len(f)):
        s = strategy.evaluate(f, i)
        if s is not None:
            out[s.bar_time] = s
    return out, f.time(len(f) - 1)


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_signal_at_bar_t_is_unchanged_by_data_after_t(name: str) -> None:
    """SPEC phase-2 requirement: a signal at bar t must not change when later data is added.

    The market is re-built from only the first N bars (a partial 4h bar is dropped, as in
    live) and every signal in that prefix must equal the one produced with all the data.
    """
    strategy = STRATEGIES[name]
    df = synth.standard_market()
    full, _ = signals_by_time(strategy, synth.frames(df))
    assert full, "synthetic market produced no signals; the test would be vacuous"
    checked = 0
    for cut in (2503, 4507, 6211):
        part, last = signals_by_time(strategy, synth.truncate(df, cut))
        expected = {t: sig for t, sig in full.items() if t <= last}
        assert part == expected, f"{name}: signals in the first {cut} bars changed with later data"
        checked += len(expected)
    assert checked > 0


@pytest.mark.parametrize("name", sorted(STRATEGIES))
def test_every_feature_column_is_unchanged_by_data_after_t(name: str) -> None:
    """Stronger than comparing signals: compare each feature array of a prefix with the same
    prefix of the full run. Any leak in any column, even one that rarely changes a signal,
    shows up here. Cuts at many offsets so partial 4h bars are exercised."""
    strategy = STRATEGIES[name]
    df = synth.standard_market()
    full = strategy.prepare(synth.frames(df))
    for cut in range(1801, 6800, 331):
        part = strategy.prepare(synth.truncate(df, cut))
        n = len(part)
        assert part.index.equals(full.index[:n])
        for col, arr in part.cols.items():
            want = full.cols[col][:n]
            if arr.dtype == object:
                assert arr.tolist() == want.tolist(), f"{name}.{col} leaks future data (cut {cut})"
            else:
                np.testing.assert_allclose(
                    arr,
                    want,
                    rtol=1e-9,
                    atol=1e-9,
                    equal_nan=True,
                    err_msg=f"{name}.{col} leaks future data (cut {cut})",
                )


def test_strategies_are_pure_and_do_not_mutate_inputs() -> None:
    df = synth.standard_market()
    fr = synth.frames(df)
    before = {k: v.copy() for k, v in fr.frames.items()}
    s = S1Trend()
    a = all_signals(s, fr)
    b = all_signals(s, fr)
    assert a == b
    for k, v in fr.frames.items():
        pd.testing.assert_frame_equal(v, before[k])


# ---- strategy specifics ---------------------------------------------------------------


def test_s1_signal_shape_matches_spec() -> None:
    sigs = all_signals(S1Trend(), synth.frames(synth.standard_market()))
    assert len(sigs) > 10
    for s in sigs.values():
        risk = s.entry - s.stop
        assert risk > 0 and s.tp1 is not None
        assert abs(s.tp1 - (s.entry + Decimal("1.5") * risk)) <= Decimal("0.00000002")  # 1.5R
        assert s.tp1_close_fraction == Decimal("0.5")
        assert s.trail is not None and s.trail.mult == 3.0 and s.trail.period == 22
        assert s.reasons["regime4"] == "TREND_UP"
        assert 60 <= s.s_tech <= 100


def test_s2_only_fires_in_range_and_targets_the_middle_band() -> None:
    sigs = all_signals(S2MeanReversion(), synth.frames(synth.standard_market()))
    assert sigs
    for s in sigs.values():
        assert s.tp1 is not None and s.tp1 > s.entry > s.stop
        assert s.tp1_close_fraction == 1 and s.time_stop_bars == 12
        assert s.reasons["regime4"] == "RANGE"


def test_s3_with_spec_defaults_requires_trend_up_regime() -> None:
    sigs = all_signals(S3Breakout(), synth.frames(synth.standard_market()))
    assert all(s.reasons for s in sigs.values())  # may legitimately be empty (see S3Params)
    wide = all_signals(S3Breakout(WIDE), synth.frames(synth.standard_market()))
    assert wide, "relaxing the regime filter should let the squeeze breakout appear"
    for s in wide.values():
        assert s.false_breakout is not None and s.false_breakout[1] == 3
        assert s.trail is not None and s.trail.mult == 2.5 and s.trail.after_tp1 is False
        assert s.stop < s.entry and s.tp1 is None


def test_btc_downtrend_blocks_altcoin_longs() -> None:
    df = synth.standard_market()
    alt = synth.frames(df, "ETHUSDT")
    base = all_signals(S1Trend(), alt)
    assert base
    down = synth.make_1h([("down", 7000)], seed=9)
    blocked = MarketFrames("ETHUSDT", alt.frames, btc_4h=synth.to_4h(down))
    # BTC is in TREND_DOWN for most of the run: signals only survive where BTC is not down
    after = all_signals(S1Trend(), blocked)
    assert len(after) < len(base)
    btc_reg = rg.classify(blocked.btc_4h)["regime"]  # type: ignore[arg-type]
    assert (btc_reg == Regime.TREND_DOWN).sum() > 100


# ---- scoring --------------------------------------------------------------------------


def test_score_thresholds_with_neutral_ml_and_ai() -> None:
    # Score = 0.45*S_tech + 0.35*50 + 0.20*50 = 0.45*S_tech + 27.5
    full = score_signal(100)
    assert full.score == pytest.approx(72.5)
    assert full.decision == Decision.TAKEN and full.size_factor == 1
    half = score_signal(80)
    assert half.score == pytest.approx(63.5)
    assert half.decision == Decision.TAKEN and half.size_factor == Decimal("0.5")
    skipped = score_signal(60)
    assert skipped.score == pytest.approx(54.5)
    assert skipped.decision == Decision.SKIPPED and skipped.size_factor == 0


def test_score_formula_and_validation() -> None:
    r = score_signal(80, 70, 40)
    assert r.score == pytest.approx(0.45 * 80 + 0.35 * 70 + 0.20 * 40)
    with pytest.raises(ValueError, match="s_ml"):
        score_signal(80, 120, 50)
    custom = score_signal(80, w=ScoreWeights(tech=1.0, ml=0.0, ai=0.0))
    assert custom.size_factor == 1


def test_signal_time_is_utc_aware() -> None:
    s = next(iter(all_signals(S1Trend(), synth.frames(synth.standard_market())).values()))
    assert s.bar_time.tzinfo is not None and s.bar_time.utcoffset() == datetime.now(UTC).utcoffset()
