from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ModelKind = Literal["logistic_regression", "random_forest"]
JobStatus = Literal["queued", "running", "completed", "failed", "cancelled"]


class TrainRequest(BaseModel):
    dataset_id: str = Field(min_length=1)
    model: ModelKind = "logistic_regression"
    features: list[str] | None = Field(
        default=None,
        description="Subset of feature columns. Defaults to all columns in the features parquet.",
    )
    seed: int = 42


class TrainingMetrics(BaseModel):
    train_rows: int
    val_rows: int
    train_accuracy: float
    val_accuracy: float
    classes: list[int]


class TrainingWindow(BaseModel):
    from_ms: int
    to_ms: int


class TrainingJob(BaseModel):
    id: str
    status: JobStatus
    dataset_id: str
    model: ModelKind
    features: list[str] = Field(default_factory=list)
    window: TrainingWindow | None = None
    metrics: TrainingMetrics | None = None
    model_path: str | None = None
    metadata_path: str | None = None
    model_id: str | None = None
    model_version: int | None = None
    error: str | None = None
    created_at_ms: int
    completed_at_ms: int | None = None


class RunResponse(BaseModel):
    job: TrainingJob
