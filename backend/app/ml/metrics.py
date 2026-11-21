"""Classification metrics (no heavy imports: the API and the registry use them too)."""

from typing import Any

import numpy as np
import pandas as pd


def auc(y: np.ndarray[Any, Any], p: np.ndarray[Any, Any]) -> float:
    """Rank-based AUC (ties averaged); nan when only one class is present."""
    pos = int(y.sum())
    neg = len(y) - pos
    if pos == 0 or neg == 0:
        return float("nan")
    ranks = pd.Series(p).rank(method="average").to_numpy()
    return float((ranks[y == 1].sum() - pos * (pos + 1) / 2) / (pos * neg))


def logloss(y: np.ndarray[Any, Any], p: np.ndarray[Any, Any]) -> float:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def metrics(y: np.ndarray[Any, Any], p: np.ndarray[Any, Any]) -> dict[str, float]:
    """AUC, log-loss, Brier, the base rate and the precision lift of the top 30% scores."""
    base = float(y.mean()) if len(y) else float("nan")
    k = max(1, int(len(y) * 0.3))
    top = np.argsort(-p)[:k]
    return {
        "n": float(len(y)),
        "auc": auc(y, p),
        "logloss": logloss(y, p),
        "brier": float(np.mean((p - y) ** 2)),
        "base_rate": base,
        "base_logloss": logloss(y, np.full(len(y), base)) if len(y) else float("nan"),
        "precision_top30": float(y[top].mean()) if len(y) else float("nan"),
    }
