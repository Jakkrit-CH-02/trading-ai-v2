from __future__ import annotations

from pydantic import BaseModel, Field


class EvaluationRequest(BaseModel):
    backtest_id: str = Field(min_length=1)
    model_id: str = Field(min_length=1)


class EvaluationMetrics(BaseModel):
    """Model-level metrics derived from a backtest result.

    precision         — fraction of closed trades that were profitable
    recall            — winners / count of bars whose return was positive
    calibration_error — |observed_win_rate - 0.5|, deviation from neutral baseline
    feature_drift     — split-half mean shift of bar returns over their stddev
    """

    total_trades: int
    winning_trades: int
    losing_trades: int
    precision: float
    recall: float
    calibration_error: float
    feature_drift: float


class EvaluationReport(BaseModel):
    id: str
    backtest_id: str
    model_id: str
    symbol: str
    interval: str
    metrics: EvaluationMetrics
    passed: bool
    reason: str
    created_at_ms: int
