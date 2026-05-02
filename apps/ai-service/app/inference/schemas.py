from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.explain.service import Explanation
from app.registry.schemas import Environment

Signal = Literal["BUY", "SELL", "HOLD"]


class PredictRequest(BaseModel):
    symbol: str = Field(min_length=1)
    timeframe: str = Field(min_length=1)
    features: dict[str, float]
    environment: Environment | None = None


class PredictResponse(BaseModel):
    symbol: str
    timeframe: str
    signal: Signal
    confidence: float
    risk_score: float
    probabilities: dict[str, float]
    model_id: str
    model_version: int
    reason: str
    cached: bool = False
    explanation: Explanation | None = None


class ReloadResponse(BaseModel):
    loaded: bool
    model_id: str | None = None
    model_version: int | None = None
    environment: Environment
