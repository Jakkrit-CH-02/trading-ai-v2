"""Signal scoring (SPEC 2.3): Score = 0.45*S_tech + 0.35*S_ml + 0.20*S_ai.

S_ml and S_ai default to 50 (neutral) until the AI layer exists (Phase 6) and whenever
the LLM/ML is unavailable. The weights are starting values, to be tuned from walk-forward
results rather than intuition.
"""

from dataclasses import dataclass
from decimal import Decimal

from app.core.models import Decision


@dataclass(frozen=True, slots=True)
class ScoreWeights:
    tech: float = 0.45
    ml: float = 0.35
    ai: float = 0.20
    full_size_at: float = 70.0
    half_size_at: float = 60.0


@dataclass(frozen=True, slots=True)
class ScoreResult:
    score: float
    s_tech: float
    s_ml: float
    s_ai: float
    decision: Decision
    size_factor: Decimal  # 1, 0.5 or 0 — the Risk Engine multiplies its own size by this
    reason: str


def score_signal(
    s_tech: float, s_ml: float = 50.0, s_ai: float = 50.0, w: ScoreWeights | None = None
) -> ScoreResult:
    w = w or ScoreWeights()
    for name, v in (("s_tech", s_tech), ("s_ml", s_ml), ("s_ai", s_ai)):
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"{name} must be within 0..100, got {v}")
    score = w.tech * s_tech + w.ml * s_ml + w.ai * s_ai
    if score >= w.full_size_at:
        return ScoreResult(score, s_tech, s_ml, s_ai, Decision.TAKEN, Decimal(1), "score >= 70")
    if score >= w.half_size_at:
        return ScoreResult(
            score, s_tech, s_ml, s_ai, Decision.TAKEN, Decimal("0.5"), "score 60-69: half size"
        )
    return ScoreResult(
        score, s_tech, s_ml, s_ai, Decision.SKIPPED, Decimal(0), f"score {score:.1f} < 60"
    )
