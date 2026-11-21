"""The decision made at the close of a bar: strategy signal -> liquidity filter -> cooldown ->
score. ONE function used by the backtester and by the live runner (SPEC principle 2), so a
bar can never be judged differently in backtest and in paper/live."""

from collections.abc import Callable
from dataclasses import dataclass

from app.core.models import Decision
from app.strategies.base import Strategy
from app.strategies.features import Features
from app.strategies.scoring import ScoreResult, ScoreWeights, score_signal
from app.strategies.types import Signal


@dataclass(frozen=True, slots=True)
class BarDecision:
    signal: Signal
    score: ScoreResult
    decision: Decision
    reason: str


def decide_at_close(
    strategy: Strategy,
    feats: Features,
    i: int,
    weights: ScoreWeights,
    min_quote_volume_24h: float,
    in_cooldown: bool,
    ml_score: Callable[[Signal], float] | None = None,
) -> BarDecision | None:
    """``None`` = the strategy has no signal on this bar. Otherwise every signal is returned
    with its fate (TAKEN / SKIPPED / REJECTED) and the reason, so it can be recorded."""
    sig = strategy.evaluate(feats, i)
    if sig is None:
        return None
    s_ml = ml_score(sig) if ml_score is not None else 50.0  # 50 = neutral, no model
    sc = score_signal(sig.s_tech, s_ml, w=weights)
    qv = feats["qv24h"][i] if "qv24h" in feats.cols else float("inf")
    if min_quote_volume_24h > 0 and not qv >= min_quote_volume_24h:
        return BarDecision(sig, sc, Decision.REJECTED, "liquidity filter")
    if in_cooldown:
        return BarDecision(sig, sc, Decision.REJECTED, "cooldown after stop")
    if sc.decision == Decision.SKIPPED:
        return BarDecision(sig, sc, Decision.SKIPPED, sc.reason)
    return BarDecision(sig, sc, Decision.TAKEN, sc.reason)
