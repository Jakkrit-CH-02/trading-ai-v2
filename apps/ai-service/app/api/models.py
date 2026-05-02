from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.registry.schemas import PromoteRequest
from app.registry.service import RegistryService
from app.registry.store import ModelNotFound, NotEvaluated


def get_registry(request: Request) -> RegistryService:
    svc = getattr(request.app.state, "registry", None)
    if svc is None:  # pragma: no cover - lifespan wires this in main.py
        raise RuntimeError("registry not configured on app state")
    return svc


router = APIRouter(prefix="/api/models", tags=["models"])


@router.get("")
async def list_models(
    registry: RegistryService = Depends(get_registry),
) -> dict[str, object]:
    models = registry.list()
    active = registry.active()
    return {
        "data": {
            "models": [m.model_dump(mode="json") for m in models],
            "active": active.model_dump(mode="json"),
        },
        "error": None,
    }


@router.post("/{model_id}/promote")
async def promote_model(
    model_id: str,
    req: PromoteRequest,
    registry: RegistryService = Depends(get_registry),
) -> dict[str, object]:
    try:
        active = registry.promote(model_id, req.environment)
    except ModelNotFound:
        raise HTTPException(
            status_code=404,
            detail={
                "data": None,
                "error": {
                    "code": "not_found",
                    "message": f"model {model_id} not found",
                },
            },
        )
    except NotEvaluated as e:
        raise HTTPException(
            status_code=400,
            detail={
                "data": None,
                "error": {"code": "validation_failed", "message": str(e)},
            },
        )
    return {
        "data": {
            "active": active.model_dump(mode="json"),
            "environment": req.environment,
            "model_id": model_id,
        },
        "error": None,
    }
