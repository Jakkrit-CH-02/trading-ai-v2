"""The ML life cycle in one place, used by the CLI and by the ml-worker:

``train_and_register``  candles -> dataset -> model -> out-of-sample backtest -> promote or keep
``monitor_model``       recent candles -> drift (PSI) and live precision -> suspend if it degrades
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.backtest.data import load_market_frames
from app.core.models import MlModel
from app.marketdata.store import CandleStore
from app.ml.evaluate import (
    Prepared,
    build_all,
    compare_backtests,
    metrics_line,
    prepare_symbols,
    verdict,
)
from app.ml.features import BASE_FEATURES, FEATURE_NAMES, PREFIX
from app.ml.registry import active_model, save_candidate, suspend
from app.ml.scorer import scorer_from_row
from app.ml.train import TrainConfig, bin_shares, psi, train_candidate
from app.strategies.base import MarketFrames

log = structlog.get_logger()
PSI_ALERT = 0.25  # a feature this far from its training distribution has drifted
PSI_FEATURES = 4  # ... and this many drifted features switch the model off
MIN_PRECISION_N = 15
MONITOR_DAYS = 60


async def load(
    store: CandleStore, symbols: list[str], start: datetime, end: datetime
) -> dict[str, MarketFrames]:
    return {s: await load_market_frames(store, s, start, end) for s in symbols}


WARMUP = ["dist_ema200", "regime"]  # NaN until the slowest indicators have enough history


def market_frame(prepared: list[Prepared]) -> pd.DataFrame:
    """The ML market-state columns of every bar of every symbol, warm-up bars excluded (every
    bar, not a stride: a stride aliases with the hour-of-day feature)."""
    parts = [pd.DataFrame({n: p.feats.cols[PREFIX + n] for n in BASE_FEATURES}) for p in prepared]
    return pd.concat(parts, ignore_index=True).dropna(subset=WARMUP)


@dataclass(slots=True)
class TrainReport:
    version: int
    promoted: bool
    reason: str
    n_signals: int
    cv: dict[str, float]
    holdout: dict[str, float]
    baseline: dict[str, Any]
    with_ml: dict[str, Any]
    backtest_summary: str


async def retrain_due(
    sessions: async_sessionmaker[AsyncSession], name: str, now: datetime, every: timedelta
) -> bool:
    """True if the strategy has no model yet or its newest one is older than ``every``. Decided
    from the database, so a restart of the worker never causes an extra training run."""
    async with sessions() as db:
        newest = (
            await db.execute(
                select(func.max(MlModel.created_at)).where(MlModel.strategy == name.upper())
            )
        ).scalar_one()
    return newest is None or now - newest >= every


async def train_and_register(
    sessions: async_sessionmaker[AsyncSession],
    store: CandleStore,
    name: str,
    symbols: list[str],
    years: float = 3.0,
    cfg: TrainConfig | None = None,
    now: datetime | None = None,
) -> TrainReport:
    cfg = cfg or TrainConfig()
    end = now or datetime.now(UTC)
    frames = await load(store, symbols, end - timedelta(days=int(years * 365.25)), end)
    prepared = prepare_symbols(name, frames)
    df = build_all(prepared)
    cand = train_candidate(df, cfg, market_frame(prepared))  # ValueError if too few signals
    cmp = compare_backtests(prepared, cand.oof, cand.base_rate)
    ok, summary = verdict(cmp)
    extra = {"baseline": metrics_line(cmp.baseline), "with_ml": metrics_line(cmp.with_ml)}
    hold = df.iloc[int(len(df) * (1 - cfg.holdout_frac)) :]
    row, promoted, reason = await save_candidate(
        sessions, name.upper(), cand, hold, backtest=(ok, summary, extra)
    )
    return TrainReport(
        row.version, promoted, reason, len(df), cand.cv, cand.holdout,
        extra["baseline"], extra["with_ml"], summary,
    )  # fmt: skip


def drift(psi_ref: dict[str, Any], recent: pd.DataFrame) -> dict[str, float]:
    """PSI of every market-state feature: stored training shares vs the recent bars."""
    out = {}
    for name in BASE_FEATURES:
        ref = psi_ref.get(name)
        if not ref or name not in recent:
            continue
        actual = bin_shares(recent[name].to_numpy(dtype=float), np.array(ref["edges"]))
        out[name] = psi(np.array(ref["shares"]), actual)
    return out


def precision_check(
    y: np.ndarray[Any, Any], p: np.ndarray[Any, Any], base_rate: float
) -> tuple[bool, str]:
    """Among signals the model likes (p above the base rate), do more win than the base rate?
    Fewer than MIN_PRECISION_N such signals => not enough evidence either way (passes)."""
    liked = p > base_rate
    n = int(liked.sum())
    if n < MIN_PRECISION_N:
        return True, f"only {n} liked signals: not enough to judge"
    prec = float(y[liked].mean())
    return prec >= base_rate, f"precision of liked signals {prec:.2f} vs base rate {base_rate:.2f}"


@dataclass(slots=True)
class MonitorReport:
    strategy: str
    version: int | None
    suspended: bool
    reason: str
    drifted: list[str]


async def monitor_model(
    sessions: async_sessionmaker[AsyncSession],
    store: CandleStore,
    name: str,
    symbols: list[str],
    now: datetime | None = None,
) -> MonitorReport:
    end = now or datetime.now(UTC)
    async with sessions() as db:
        m: MlModel | None = await active_model(db, name.upper())
    if m is None:
        return MonitorReport(name.upper(), None, False, "no active model", [])
    # history for the indicators' warm-up + the monitoring window
    frames = await load(store, symbols, end - timedelta(days=MONITOR_DAYS + 120), end)
    prepared = prepare_symbols(name, frames)
    cut = pd.Timestamp(end - timedelta(days=MONITOR_DAYS))
    recent = pd.concat(
        [
            pd.DataFrame(
                {n: p.feats.cols[PREFIX + n] for n in BASE_FEATURES}, index=p.feats.index
            ).loc[cut:]
            for p in prepared
        ]
    ).dropna(subset=WARMUP)
    d = drift(m.psi_ref, recent)
    drifted = sorted(k for k, v in d.items() if v > PSI_ALERT)
    ds = build_all(prepared)
    ds = ds[ds["t"] >= cut]
    ok_prec, prec_msg = True, "no recent resolved signals"
    if len(ds):
        scorer = scorer_from_row(m)
        p = np.asarray(scorer.booster.predict(ds[FEATURE_NAMES].to_numpy()), dtype=float)
        ok_prec, prec_msg = precision_check(ds["y"].to_numpy(), p, scorer.base_rate)
    reasons = []
    if len(drifted) >= PSI_FEATURES:
        reasons.append(f"feature drift: {', '.join(drifted)}")
    if not ok_prec:
        reasons.append(prec_msg)
    if reasons:
        await suspend(sessions, m.id, "; ".join(reasons))
        log.warning("ml.suspended", strategy=name, reasons=reasons)
    return MonitorReport(
        name.upper(), m.version, bool(reasons), "; ".join(reasons) or prec_msg, drifted
    )
