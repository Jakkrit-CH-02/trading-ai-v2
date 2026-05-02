from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.inference.schemas import (
    PredictRequest,
    PredictResponse,
    ReloadResponse,
)
from app.inference.service import (
    FeatureSchemaMismatch,
    InferenceService,
    ModelUnavailable,
)


def get_inference(request: Request) -> InferenceService:
    svc = getattr(request.app.state, "inference", None)
    if svc is None:  # pragma: no cover - lifespan wires this in main.py
        raise RuntimeError("inference service not configured on app state")
    return svc


router = APIRouter(prefix="/api", tags=["inference"])


@router.post("/predict")
async def predict(
    req: PredictRequest,
    explain: bool = False,
    inference: InferenceService = Depends(get_inference),
) -> dict[str, object]:
    try:
        resp = inference.predict(req, explain=explain)
    except ModelUnavailable as e:
        # Fallback per requirement: return a HOLD signal with model_unavailable.
        fallback = PredictResponse(
            symbol=req.symbol,
            timeframe=req.timeframe,
            signal="HOLD",
            confidence=0.0,
            risk_score=1.0,
            probabilities={},
            model_id="",
            model_version=0,
            reason="model unavailable; defaulting to HOLD",
        )
        raise HTTPException(
            status_code=503,
            detail={
                "data": fallback.model_dump(mode="json"),
                "error": {"code": "model_unavailable", "message": str(e)},
            },
        )
    except FeatureSchemaMismatch as e:
        raise HTTPException(
            status_code=400,
            detail={
                "data": None,
                "error": {"code": "validation_failed", "message": str(e)},
            },
        )
    return {"data": resp.model_dump(mode="json"), "error": None}


@router.post("/predict/reload")
async def reload_model(
    inference: InferenceService = Depends(get_inference),
) -> dict[str, object]:
    loaded = inference.reload()
    body = ReloadResponse(
        loaded=loaded,
        model_id=inference.model_id,
        model_version=inference.model_version,
        environment=inference.environment,
    )
    return {"data": body.model_dump(mode="json"), "error": None}
