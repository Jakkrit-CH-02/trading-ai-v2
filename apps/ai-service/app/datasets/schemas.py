from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

LabelKind = Literal["next_direction", "future_return", "threshold_move"]


class LabelConfig(BaseModel):
    kind: LabelKind = "next_direction"
    horizon: int = Field(default=1, ge=1, description="Bars ahead used for label.")
    threshold: float = Field(
        default=0.0,
        description="Return threshold for threshold_move (e.g. 0.005 == 0.5%).",
    )


class SplitConfig(BaseModel):
    train: float = 0.7
    val: float = 0.15
    test: float = 0.15

    @field_validator("test")
    @classmethod
    def _sums_to_one(cls, v: float, info) -> float:
        train = info.data.get("train", 0.0)
        val = info.data.get("val", 0.0)
        total = train + val + v
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"split fractions must sum to 1.0 (got {total})")
        return v


class BuildRequest(BaseModel):
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1, description="e.g. 1m, 5m, 1h.")
    from_ms: int = Field(ge=0, description="Inclusive start, Unix ms UTC.")
    to_ms: int = Field(gt=0, description="Exclusive end, Unix ms UTC.")
    label: LabelConfig = LabelConfig()
    split: SplitConfig = SplitConfig()

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()

    @field_validator("to_ms")
    @classmethod
    def _ordered(cls, v: int, info) -> int:
        f = info.data.get("from_ms")
        if f is not None and v <= f:
            raise ValueError("to_ms must be greater than from_ms")
        return v


class DatasetMetadata(BaseModel):
    """Persisted alongside each parquet file as <name>.json."""

    id: str
    symbol: str
    timeframe: str
    from_ms: int
    to_ms: int
    rows: int
    label: LabelConfig
    split: SplitConfig
    path: str
    created_at_ms: int


class BuildResponse(BaseModel):
    dataset: DatasetMetadata


class ListResponse(BaseModel):
    datasets: list[DatasetMetadata]
