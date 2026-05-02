from __future__ import annotations

from pydantic import BaseModel, Field


class ComputeRequest(BaseModel):
    dataset_id: str = Field(min_length=1)
    features: list[str] | None = Field(
        default=None,
        description="Subset of feature names. Defaults to DEFAULT_FEATURES.",
    )


class FeatureMetadata(BaseModel):
    dataset_id: str
    path: str
    rows: int
    features: list[str]
    created_at_ms: int


class ComputeResponse(BaseModel):
    features: FeatureMetadata
