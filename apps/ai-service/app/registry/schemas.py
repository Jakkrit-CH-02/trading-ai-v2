from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Environment = Literal["paper", "live"]


class ModelMetadata(BaseModel):
    id: str
    version: int
    dataset_id: str
    feature_schema_id: str | None = None
    feature_names: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    artifact_path: str
    created_at_ms: int
    evaluated: bool = False


class RegisterRequest(BaseModel):
    dataset_id: str = Field(min_length=1)
    feature_schema_id: str | None = None
    metrics: dict[str, float] = Field(default_factory=dict)
    evaluated: bool = False


class PromoteRequest(BaseModel):
    environment: Environment


class ActiveModels(BaseModel):
    paper: str | None = None
    live: str | None = None
