from __future__ import annotations

import json
import logging
import secrets
import time
from pathlib import Path

import joblib
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from app.datasets.builder import DatasetBuilder
from app.registry.service import RegistryService

from .schemas import (
    ModelKind,
    TrainingJob,
    TrainingMetrics,
    TrainingWindow,
    TrainRequest,
)

log = logging.getLogger(__name__)


class DatasetNotFound(Exception):
    pass


class FeaturesNotFound(Exception):
    pass


class TrainingError(Exception):
    pass


def _job_id() -> str:
    return f"{int(time.time() * 1000):013x}{secrets.token_hex(4)}"


def _build_estimator(kind: ModelKind, seed: int):
    match kind:
        case "logistic_regression":
            return Pipeline(
                [
                    ("scaler", StandardScaler()),
                    (
                        "clf",
                        LogisticRegression(
                            max_iter=1000, random_state=seed, n_jobs=None
                        ),
                    ),
                ]
            )
        case "random_forest":
            return RandomForestClassifier(
                n_estimators=50, random_state=seed, n_jobs=1
            )


class Trainer:
    """Train classifiers from a features parquet + dataset labels.

    Persists `model.joblib` and `metadata.json` per job under `root/{job_id}/`.
    Jobs are tracked in-process; the service is stateless across restarts —
    durable job state belongs in the Go backend per CLAUDE.md.
    """

    def __init__(
        self,
        *,
        builder: DatasetBuilder,
        features_root: Path,
        models_root: Path,
        registry: RegistryService | None = None,
    ) -> None:
        self._builder = builder
        self._features_root = features_root
        self._models_root = models_root
        self._models_root.mkdir(parents=True, exist_ok=True)
        self._registry = registry
        self._jobs: dict[str, TrainingJob] = {}

    def get(self, job_id: str) -> TrainingJob | None:
        return self._jobs.get(job_id)

    def run(self, req: TrainRequest) -> TrainingJob:
        job = TrainingJob(
            id=_job_id(),
            status="queued",
            dataset_id=req.dataset_id,
            model=req.model,
            created_at_ms=int(time.time() * 1000),
        )
        self._jobs[job.id] = job
        try:
            return self._execute(job, req)
        except (DatasetNotFound, FeaturesNotFound, TrainingError) as e:
            job.status = "failed"
            job.error = str(e)
            job.completed_at_ms = int(time.time() * 1000)
            log.error(
                "training failed",
                extra={"job_id": job.id, "dataset_id": req.dataset_id, "err": str(e)},
            )
            return job

    def _execute(self, job: TrainingJob, req: TrainRequest) -> TrainingJob:
        job.status = "running"

        ds_meta = next(
            (d for d in self._builder.list() if d.id == req.dataset_id), None
        )
        if ds_meta is None:
            raise DatasetNotFound(req.dataset_id)

        feat_path = self._features_root / f"{req.dataset_id}.parquet"
        if not feat_path.exists():
            raise FeaturesNotFound(str(feat_path))

        features_df = pd.read_parquet(feat_path)
        dataset_df = pd.read_parquet(ds_meta.path)[["open_time", "label", "split"]]

        merged = features_df.merge(dataset_df, on="open_time", how="inner").dropna(
            subset=["label"]
        )
        if merged.empty:
            raise TrainingError("no rows after joining features with labels")

        feature_cols = (
            list(req.features)
            if req.features is not None
            else [c for c in features_df.columns if c != "open_time"]
        )
        missing = [c for c in feature_cols if c not in merged.columns]
        if missing:
            raise TrainingError(f"missing feature columns: {missing}")

        train_df = merged[merged["split"] == "train"]
        val_df = merged[merged["split"] == "val"]
        if train_df.empty:
            raise TrainingError("no training rows in 'train' split")

        x_train = train_df[feature_cols].to_numpy(dtype="float64")
        y_train = train_df["label"].astype("int64").to_numpy()

        if len(set(y_train.tolist())) < 2:
            raise TrainingError("training labels have a single class — cannot fit classifier")

        estimator = _build_estimator(req.model, req.seed)
        estimator.fit(x_train, y_train)

        train_pred = estimator.predict(x_train)
        train_acc = float(accuracy_score(y_train, train_pred))

        if not val_df.empty:
            x_val = val_df[feature_cols].to_numpy(dtype="float64")
            y_val = val_df["label"].astype("int64").to_numpy()
            val_pred = estimator.predict(x_val)
            val_acc = float(accuracy_score(y_val, val_pred))
            val_rows = int(len(val_df))
        else:
            val_acc = float("nan")
            val_rows = 0

        out_dir = self._models_root / job.id
        out_dir.mkdir(parents=True, exist_ok=True)
        model_path = out_dir / "model.joblib"
        meta_path = out_dir / "metadata.json"
        joblib.dump(estimator, model_path)

        window = TrainingWindow(
            from_ms=int(merged["open_time"].iloc[0]),
            to_ms=int(merged["open_time"].iloc[-1]),
        )
        metrics = TrainingMetrics(
            train_rows=int(len(train_df)),
            val_rows=val_rows,
            train_accuracy=train_acc,
            val_accuracy=val_acc,
            classes=sorted({int(c) for c in y_train.tolist()}),
        )

        job.status = "completed"
        job.features = feature_cols
        job.window = window
        job.metrics = metrics
        job.model_path = str(model_path)
        job.metadata_path = str(meta_path)
        job.completed_at_ms = int(time.time() * 1000)

        if self._registry is not None:
            registered = self._registry.register(
                estimator=estimator,
                dataset_id=req.dataset_id,
                feature_names=feature_cols,
                metrics={
                    "train_accuracy": metrics.train_accuracy,
                    "val_accuracy": metrics.val_accuracy,
                    "train_rows": float(metrics.train_rows),
                    "val_rows": float(metrics.val_rows),
                },
                evaluated=metrics.val_rows > 0,
            )
            job.model_id = registered.id
            job.model_version = registered.version

        meta_path.write_text(job.model_dump_json())
        log.info(
            "training completed",
            extra={
                "job_id": job.id,
                "dataset_id": req.dataset_id,
                "model": req.model,
                "train_rows": metrics.train_rows,
                "val_rows": metrics.val_rows,
            },
        )
        return job
