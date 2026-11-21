"""S_ml for a signal (SPEC 2.3): the model's win probability, centred on the base rate.

The score is neutral (50) when the model's probability equals the share of signals that won in
training, higher when the model is more optimistic than usual and lower when less. Centring matters:
a raw ``100 x p`` would sit below 50 for almost every signal (most signals lose) and silently veto
the whole strategy. No model, no target, NaN inputs or any error => exactly 50.
"""

import math
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import MlModel, MlModelStatus
from app.ml.features import PREFIX, row_vector
from app.ml.labels import target_of
from app.strategies.features import Features
from app.strategies.types import Signal

if TYPE_CHECKING:
    import lightgbm as lgb

log = structlog.get_logger()
NEUTRAL = 50.0
SCALE = 100.0  # +0.10 probability over the base rate = +10 points


def p_to_score(p: float, base_rate: float) -> float:
    if not math.isfinite(p) or not math.isfinite(base_rate):
        return NEUTRAL
    return float(min(100.0, max(0.0, NEUTRAL + SCALE * (p - base_rate))))


@dataclass(slots=True)
class MlScorer:
    booster: "lgb.Booster"
    base_rate: float
    version: int

    def probability(self, feats: Features, i: int, sig: Signal) -> float | None:
        tp = target_of(sig)
        if tp is None or PREFIX + "rsi14" not in feats.cols:
            return None
        x = row_vector(feats, i, sig.s_tech, float(sig.entry), float(sig.stop), tp)
        return float(self.booster.predict(np.array([x]))[0])

    def s_ml(self, feats: Features, i: int, sig: Signal) -> float:
        try:
            p = self.probability(feats, i, sig)
        except Exception:  # a scoring problem must never stop a bot: fall back to neutral
            log.exception("ml.score_failed")
            return NEUTRAL
        return NEUTRAL if p is None else p_to_score(p, self.base_rate)

    def for_bar(self, feats: Features, i: int) -> Callable[[Signal], float]:
        return lambda sig: self.s_ml(feats, i, sig)


def scorer_from_row(m: MlModel) -> MlScorer:
    import lightgbm as lgb  # imported here so modules that only import the pool stay light

    base = float(((m.metrics or {}).get("train") or {}).get("base_rate") or math.nan)
    return MlScorer(lgb.Booster(model_str=m.model_text), base, m.version)


class ScorerPool:
    """Active scorers per strategy, re-read from the database every ``ttl_s`` seconds."""

    def __init__(self, sessions: async_sessionmaker[AsyncSession], ttl_s: float = 300.0) -> None:
        self.sessions = sessions
        self.ttl_s = ttl_s
        self._cache: dict[str, tuple[float, MlScorer | None]] = {}

    async def get(self, strategy: str, now: float) -> MlScorer | None:
        hit = self._cache.get(strategy)
        if hit is not None and now - hit[0] < self.ttl_s:
            return hit[1]
        scorer: MlScorer | None = None
        try:
            async with self.sessions() as db:
                row: Any = (
                    await db.execute(
                        select(MlModel).where(
                            MlModel.strategy == strategy.upper(),
                            MlModel.status == MlModelStatus.ACTIVE,
                        )
                    )
                ).scalar_one_or_none()
            scorer = scorer_from_row(row) if row is not None else None
        except Exception:
            log.exception("ml.load_failed", strategy=strategy)
        self._cache[strategy] = (now, scorer)
        return scorer
