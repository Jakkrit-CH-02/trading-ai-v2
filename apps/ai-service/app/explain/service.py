from __future__ import annotations

from typing import Any, Sequence

import numpy as np
from pydantic import BaseModel, Field


class FeatureContribution(BaseModel):
    name: str
    value: float
    importance: float
    contribution: float


class Explanation(BaseModel):
    reason: str
    top_features: list[str]
    contributions: list[FeatureContribution] = Field(default_factory=list)
    confidence_explanation: str


def _extract_importance(estimator: Any, n: int) -> np.ndarray:
    """Return a length-n importance vector derived from the estimator.

    Order of preference:
      1. `feature_importances_` (tree-based models)
      2. absolute `coef_` collapsed across classes (linear models)
      3. uniform 1/n fallback for estimators that expose neither
    """
    fi = getattr(estimator, "feature_importances_", None)
    if fi is not None:
        arr = np.asarray(fi, dtype="float64").ravel()
        if arr.shape[0] == n:
            return arr

    coef = getattr(estimator, "coef_", None)
    if coef is not None:
        arr = np.abs(np.asarray(coef, dtype="float64"))
        if arr.ndim == 2:
            arr = arr.mean(axis=0)
        arr = arr.ravel()
        if arr.shape[0] == n:
            total = arr.sum()
            return arr / total if total > 0 else np.full(n, 1.0 / n)

    return np.full(n, 1.0 / n, dtype="float64")


def _reason(signal: str, top: list[FeatureContribution]) -> str:
    if not top:
        return f"signal={signal}"
    parts = [f"{c.name}({c.contribution:+.3f})" for c in top]
    return f"signal={signal} driven by " + ", ".join(parts)


def _confidence_explanation(confidence: float, signal: str) -> str:
    if confidence >= 0.75:
        band = "high"
    elif confidence >= 0.55:
        band = "medium"
    else:
        band = "low"
    return f"confidence is {band} ({confidence:.2f}) for {signal}"


def build_explanation(
    *,
    estimator: Any,
    feature_names: Sequence[str],
    values: Sequence[float],
    signal: str,
    confidence: float,
    top_k: int = 3,
) -> Explanation:
    """Produce a deterministic per-prediction explanation.

    Contributions are `value * importance`; top_features are ranked by
    absolute contribution. Ties break by the original feature order so
    the same input always yields the same explanation.
    """
    if len(feature_names) != len(values):
        raise ValueError(
            f"feature/values length mismatch: {len(feature_names)} vs {len(values)}"
        )

    n = len(feature_names)
    importance = _extract_importance(estimator, n)
    vals = np.asarray(values, dtype="float64")
    contribs = vals * importance

    items = [
        FeatureContribution(
            name=str(feature_names[i]),
            value=float(vals[i]),
            importance=float(importance[i]),
            contribution=float(contribs[i]),
        )
        for i in range(n)
    ]
    ranked = sorted(
        enumerate(items),
        key=lambda kv: (-abs(kv[1].contribution), kv[0]),
    )
    top = [it for _, it in ranked[: max(0, top_k)]]

    return Explanation(
        reason=_reason(signal, top),
        top_features=[c.name for c in top],
        contributions=items,
        confidence_explanation=_confidence_explanation(confidence, signal),
    )
