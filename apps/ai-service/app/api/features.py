from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.features.schemas import ComputeRequest, ComputeResponse
from app.features.service import DatasetNotFound, FeatureService


def get_service(request: Request) -> FeatureService:
    svc = getattr(request.app.state, "feature_service", None)
    if svc is None:  # pragma: no cover - lifespan wires this in main.py
        raise RuntimeError("feature_service not configured on app state")
    return svc


router = APIRouter(prefix="/api/features", tags=["features"])


@router.post("/compute")
async def compute_features_endpoint(
    req: ComputeRequest,
    svc: FeatureService = Depends(get_service),
) -> dict[str, object]:
    try:
        meta = svc.compute(req.dataset_id, req.features)
    except DatasetNotFound:
        raise HTTPException(
            status_code=404,
            detail={
                "data": None,
                "error": {
                    "code": "not_found",
                    "message": f"dataset {req.dataset_id} not found",
                },
            },
        )
    except ValueError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "data": None,
                "error": {"code": "validation_failed", "message": str(e)},
            },
        )
    return {
        "data": ComputeResponse(features=meta).model_dump(mode="json"),
        "error": None,
    }
