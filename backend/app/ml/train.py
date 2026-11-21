"""Training with purged walk-forward validation (SPEC 4.1).

Why "purged": a label looks up to N bars into the future, so a training sample whose outcome
window overlaps the test period leaks the answer. Forward-chaining folds drop every training
sample whose label resolved after (test start - embargo). Only the out-of-fold (OOF) numbers are
ever reported; the final model is fit on everything and is judged on a holdout it never saw.
"""

import math
from dataclasses import dataclass
from itertools import pairwise
from typing import Any

import lightgbm as lgb
import numpy as np
import optuna
import pandas as pd

from app.ml.features import BASE_FEATURES, FEATURE_NAMES
from app.ml.metrics import logloss, metrics

optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass(frozen=True, slots=True)
class TrainConfig:
    n_folds: int = 5
    min_train_frac: float = 0.4
    holdout_frac: float = 0.2
    embargo_hours: int = 24
    optuna_trials: int = 25
    seed: int = 7
    min_samples: int = 150

    @property
    def embargo(self) -> pd.Timedelta:
        return pd.Timedelta(hours=self.embargo_hours)


def purged_splits(
    df: pd.DataFrame, n_folds: int, min_train_frac: float, embargo: pd.Timedelta
) -> list[tuple[np.ndarray[Any, Any], np.ndarray[Any, Any]]]:
    """Forward-chaining (train_idx, test_idx) pairs over ``df`` (sorted by ``t``)."""
    n = len(df)
    first = int(n * min_train_frac)
    edges = np.linspace(first, n, n_folds + 1).astype(int)
    t, t_end = df["t"].to_numpy(), df["t_end"].to_numpy()
    out = []
    for a, b in pairwise(edges):
        if b <= a:
            continue
        t0 = t[a]
        train = np.flatnonzero(t_end < t0 - embargo.to_timedelta64())
        out.append((train, np.arange(a, b)))
    return out


def lgb_params(trial_params: dict[str, Any], seed: int) -> dict[str, Any]:
    return {
        "objective": "binary", "verbosity": -1, "seed": seed, "deterministic": True,
        "force_row_wise": True, "num_threads": 2, "bagging_freq": 1, **trial_params,
    }  # fmt: skip


def fit(
    x: np.ndarray[Any, Any], y: np.ndarray[Any, Any], params: dict[str, Any], rounds: int, seed: int
) -> lgb.Booster:
    ds = lgb.Dataset(x, label=y, feature_name=FEATURE_NAMES, free_raw_data=False)
    return lgb.train(lgb_params(params, seed), ds, num_boost_round=rounds)


def oof_predictions(
    df: pd.DataFrame, params: dict[str, Any], rounds: int, cfg: TrainConfig
) -> pd.DataFrame:
    """Out-of-fold probabilities for every sample that lands in a test block."""
    x, y = df[FEATURE_NAMES].to_numpy(), df["y"].to_numpy()
    parts = []
    for tr, te in purged_splits(df, cfg.n_folds, cfg.min_train_frac, cfg.embargo):
        if len(tr) < 30 or len(np.unique(y[tr])) < 2:
            continue
        booster = fit(x[tr], y[tr], params, rounds, cfg.seed)
        parts.append(df.iloc[te][["symbol", "t", "y"]].assign(p=booster.predict(x[te])))
    return pd.concat(parts) if parts else pd.DataFrame(columns=["symbol", "t", "y", "p"])


def tune(df: pd.DataFrame, cfg: TrainConfig) -> tuple[dict[str, Any], int]:
    """Optuna search minimising the pooled OOF log-loss (small, regularised models only)."""

    def objective(trial: optuna.Trial) -> float:
        params = {
            "learning_rate": trial.suggest_float("learning_rate", 0.02, 0.15, log=True),
            "num_leaves": trial.suggest_int("num_leaves", 3, 15),
            "min_data_in_leaf": trial.suggest_int("min_data_in_leaf", 15, 80),
            "feature_fraction": trial.suggest_float("feature_fraction", 0.5, 1.0),
            "bagging_fraction": trial.suggest_float("bagging_fraction", 0.5, 1.0),
            "lambda_l2": trial.suggest_float("lambda_l2", 0.1, 20.0, log=True),
        }
        rounds = trial.suggest_int("rounds", 30, 250)
        oof = oof_predictions(df, params, rounds, cfg)
        if oof.empty:
            return math.inf
        return logloss(oof["y"].to_numpy(), oof["p"].to_numpy())

    study = optuna.create_study(
        direction="minimize", sampler=optuna.samplers.TPESampler(seed=cfg.seed)
    )
    study.optimize(objective, n_trials=cfg.optuna_trials)
    best = dict(study.best_params)
    return best, int(best.pop("rounds"))


def psi_reference(df: pd.DataFrame) -> dict[str, Any]:
    """Per-feature decile edges + bin shares of the training data, for drift monitoring.
    ``df`` holds the market-state features (BASE_FEATURES) of ALL bars, not only signal bars."""
    ref: dict[str, Any] = {}
    for name in BASE_FEATURES:
        v = df[name].to_numpy(dtype=float)
        ok = v[~np.isnan(v)]
        edges = np.unique(np.quantile(ok, np.linspace(0.1, 0.9, 9))) if len(ok) else np.array([])
        ref[name] = {"edges": edges.tolist(), "shares": bin_shares(v, edges).tolist()}
    return ref


def bin_shares(v: np.ndarray[Any, Any], edges: np.ndarray[Any, Any]) -> np.ndarray[Any, Any]:
    """Shares over len(edges)+1 value bins plus a final NaN bin."""
    nan = np.isnan(v)
    idx = np.searchsorted(edges, v[~nan], side="right")
    counts = np.bincount(idx, minlength=len(edges) + 1).astype(float)
    counts = np.append(counts, float(nan.sum()))
    shares: np.ndarray[Any, Any] = counts / max(1.0, counts.sum())
    return shares


def psi(expected: np.ndarray[Any, Any], actual: np.ndarray[Any, Any]) -> float:
    e, a = np.clip(expected, 1e-4, None), np.clip(actual, 1e-4, None)
    return float(np.sum((a - e) * np.log(a / e)))


@dataclass(slots=True)
class Candidate:
    booster_text: str
    params: dict[str, Any]
    rounds: int
    cv: dict[str, float]  # pooled out-of-fold metrics (all folds)
    holdout: dict[str, float]  # metrics on the last holdout_frac, model never saw it
    oof: pd.DataFrame  # out-of-fold probabilities (symbol, t, y, p) for backtesting S_ml
    psi_ref: dict[str, Any]
    trained_from: pd.Timestamp
    trained_to: pd.Timestamp
    n_samples: int
    base_rate: float  # share of winning signals in the training data (centres S_ml at 50)


def train_candidate(
    df: pd.DataFrame, cfg: TrainConfig | None = None, market: pd.DataFrame | None = None
) -> Candidate:
    cfg = cfg or TrainConfig()
    df = df.sort_values("t").reset_index(drop=True)
    if len(df) < cfg.min_samples or df["y"].nunique() < 2:
        raise ValueError(f"not enough labelled signals to train ({len(df)} < {cfg.min_samples})")
    cut = int(len(df) * (1 - cfg.holdout_frac))
    dev, hold = df.iloc[:cut], df.iloc[cut:]
    params, rounds = tune(dev, cfg)
    oof = oof_predictions(dev, params, rounds, cfg)
    cv = metrics(oof["y"].to_numpy(), oof["p"].to_numpy(dtype=float)) if len(oof) else {}
    # the holdout check: fit on dev samples whose outcome was known before the holdout started
    t0 = hold["t"].iloc[0]
    fit_dev = dev[dev["t_end"] < t0 - cfg.embargo]
    probe = fit(
        fit_dev[FEATURE_NAMES].to_numpy(), fit_dev["y"].to_numpy(), params, rounds, cfg.seed
    )
    hold_p = np.asarray(probe.predict(hold[FEATURE_NAMES].to_numpy()), dtype=float)
    hm = metrics(hold["y"].to_numpy(), hold_p)
    final = fit(df[FEATURE_NAMES].to_numpy(), df["y"].to_numpy(), params, rounds, cfg.seed)
    return Candidate(
        booster_text=final.model_to_string(),
        params={**params, "rounds": rounds},
        rounds=rounds,
        cv=cv,
        holdout=hm,
        oof=oof,
        psi_ref=psi_reference(market if market is not None else df),
        trained_from=df["t"].iloc[0],
        trained_to=df["t"].iloc[-1],
        n_samples=len(df),
        base_rate=float(df["y"].mean()),
    )
