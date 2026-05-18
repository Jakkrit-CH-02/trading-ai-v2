from __future__ import annotations

import logging

import pandas as pd
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.features.pipeline import compute_features
from app.inference.schemas import PredictRequest
from app.inference.service import InferenceService, ModelUnavailable

log = logging.getLogger(__name__)

router = APIRouter(prefix="/v1", tags=["infer"])

MIN_BARS = 34  # minimum bars needed for all 14 features to be non-NaN after dropna


class InferBar(BaseModel):
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class InferRequest(BaseModel):
    symbol: str
    interval: str
    bars: list[InferBar]


class InferResponse(BaseModel):
    action: str          # "buy" | "sell" | "hold"
    confidence: float
    model_version: str


_HOLD = InferResponse(action="hold", confidence=0.0, model_version="")


def get_inference(request: Request) -> InferenceService:
    svc = getattr(request.app.state, "inference", None)
    if svc is None:  # pragma: no cover
        raise RuntimeError("inference service not configured on app state")
    return svc


@router.post("/infer")
def infer(
    req: InferRequest,
    inference: InferenceService = Depends(get_inference),
) -> dict[str, object]:
    if len(req.bars) < MIN_BARS:
        return {"data": _HOLD.model_dump(), "error": None}

    df = pd.DataFrame([b.model_dump() for b in req.bars])
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)

    feat_df = compute_features(df, dropna=True)
    if feat_df.empty:
        return {"data": _HOLD.model_dump(), "error": None}

    last = feat_df.iloc[-1]
    features = {col: float(last[col]) for col in feat_df.columns if col != "open_time"}

    pred_req = PredictRequest(
        symbol=req.symbol,
        timeframe=req.interval,
        features=features,
    )

    try:
        resp = inference.predict(pred_req)
    except ModelUnavailable:
        return {"data": _HOLD.model_dump(), "error": None}

    result = InferResponse(
        action=resp.signal.lower(),
        confidence=resp.confidence,
        model_version=str(resp.model_version) if resp.model_version is not None else "",
    )
    return {"data": result.model_dump(), "error": None}
