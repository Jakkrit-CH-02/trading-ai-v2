"""Model registry: save candidates, promote only on evidence, roll back, suspend (SPEC 4.1).

Promotion rule (all must hold, on the HOLDOUT the candidate never trained on):
- at least ``MIN_HOLDOUT`` samples;
- candidate AUC >= MIN_AUC (it must beat a coin flip by a margin) and log-loss below the
  base-rate log-loss (it must beat "always predict the average");
- with an active model: candidate beats it on the same holdout in both AUC and log-loss.
Otherwise the candidate is stored as ``candidate`` and the active model (or neutral S_ml = 50)
stays. Nothing is ever deleted: rollback re-activates the previous version.
"""

from typing import TYPE_CHECKING, Any

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import MlModel, MlModelStatus
from app.ml.features import FEATURE_NAMES
from app.ml.metrics import metrics

if TYPE_CHECKING:
    from app.ml.train import Candidate

MIN_HOLDOUT = 30
MIN_AUC = 0.55


def clean(x: Any) -> Any:
    """JSON-safe metrics (NaN -> None)."""
    if isinstance(x, dict):
        return {k: clean(v) for k, v in x.items()}
    if isinstance(x, float) and x != x:
        return None
    return x


def evaluate_text(model_text: str, df: pd.DataFrame) -> dict[str, float]:
    """Metrics of a stored model on a labelled frame."""
    import lightgbm as lgb

    b = lgb.Booster(model_str=model_text)
    p = np.asarray(b.predict(df[FEATURE_NAMES].to_numpy()), dtype=float)
    return metrics(df["y"].to_numpy(), p)


def promotion_decision(
    cand: dict[str, float], champion: dict[str, float] | None
) -> tuple[bool, str]:
    n, a, ll, base = (
        cand.get("n", 0),
        cand.get("auc"),
        cand.get("logloss"),
        cand.get("base_logloss"),
    )
    if n < MIN_HOLDOUT or a is None or ll is None or base is None or a != a:
        return False, f"holdout too small or undefined (n={n:.0f})"
    if a < MIN_AUC:
        return False, f"holdout AUC {a:.3f} < {MIN_AUC}: no better than chance"
    if ll >= base:
        return False, "holdout log-loss does not beat the base rate"
    if champion is not None:
        ca, cl = champion.get("auc", float("nan")), champion.get("logloss", float("inf"))
        if not (a > ca and ll < cl):
            return (
                False,
                f"does not beat the active model on the same holdout (AUC {a:.3f} vs {ca:.3f})",
            )
    return True, f"holdout AUC {a:.3f}, log-loss {ll:.4f} < base {base:.4f}"


async def active_model(db: AsyncSession, strategy: str) -> MlModel | None:
    q = select(MlModel).where(MlModel.strategy == strategy, MlModel.status == MlModelStatus.ACTIVE)
    return (await db.execute(q)).scalar_one_or_none()


async def save_candidate(
    sessions: async_sessionmaker[AsyncSession],
    strategy: str,
    cand: "Candidate",
    holdout_df: pd.DataFrame,
    note: str | None = None,
    backtest: tuple[bool, str, dict[str, Any]] | None = None,
) -> tuple[MlModel, bool, str]:
    """Store ``cand``; promote it if the rule says so. Returns (row, promoted, reason)."""
    async with sessions.begin() as db:
        champ = await active_model(db, strategy)
        champ_metrics = (
            evaluate_text(champ.model_text, holdout_df) if champ and len(holdout_df) else None
        )
        ok, reason = promotion_decision(cand.holdout, champ_metrics)
        if ok and backtest is not None and not backtest[0]:
            ok, reason = False, f"out-of-sample backtest does not improve: {backtest[1]}"
        last = (
            await db.execute(
                select(MlModel.version)
                .where(MlModel.strategy == strategy)
                .order_by(MlModel.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        bt_info = (
            None
            if backtest is None
            else {"improves": backtest[0], "summary": backtest[1], **backtest[2]}
        )
        if ok and champ is not None:
            champ.status = MlModelStatus.RETIRED
        row = MlModel(
            strategy=strategy,
            version=(last or 0) + 1,
            status=MlModelStatus.ACTIVE if ok else MlModelStatus.CANDIDATE,
            trained_from=cand.trained_from.to_pydatetime(),
            trained_to=cand.trained_to.to_pydatetime(),
            n_samples=cand.n_samples,
            metrics=clean(
                {
                    "cv": cand.cv,
                    "holdout": cand.holdout,
                    "champion_holdout": champ_metrics,
                    "train": {"base_rate": cand.base_rate, "n": cand.n_samples},
                    "backtest": bt_info,
                    "promotion": {"promoted": ok, "reason": reason},
                }
            ),
            params=cand.params,
            psi_ref=cand.psi_ref,
            model_text=cand.booster_text,
            note=note,
        )  # fmt: skip
        db.add(row)
        await db.flush()
        return row, ok, reason


async def rollback(sessions: async_sessionmaker[AsyncSession], strategy: str) -> MlModel | None:
    """Re-activate the newest retired version (the current one becomes retired).
    ``None`` if there is nothing to go back to."""
    async with sessions.begin() as db:
        prev = (
            await db.execute(
                select(MlModel)
                .where(MlModel.strategy == strategy, MlModel.status == MlModelStatus.RETIRED)
                .order_by(MlModel.version.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if prev is None:
            return None
        cur = await active_model(db, strategy)
        if cur is not None:
            cur.status = MlModelStatus.RETIRED
        prev.status = MlModelStatus.ACTIVE
        return prev


async def suspend(sessions: async_sessionmaker[AsyncSession], model_id: Any, reason: str) -> None:
    async with sessions.begin() as db:
        m = await db.get(MlModel, model_id)
        if m is not None and m.status == MlModelStatus.ACTIVE:
            m.status = MlModelStatus.SUSPENDED
            m.note = reason[:500]
