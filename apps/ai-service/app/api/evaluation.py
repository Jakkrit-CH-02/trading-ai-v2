from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.clients.backend import BackendError
from app.evaluation.schemas import EvaluationRequest
from app.evaluation.service import (
    BacktestNotFound,
    EvaluationNotFound,
    EvaluationService,
)
from app.registry.store import ModelNotFound


def get_evaluation(request: Request) -> EvaluationService:
    svc = getattr(request.app.state, "evaluation", None)
    if svc is None:  # pragma: no cover - lifespan wires this in main.py
        raise RuntimeError("evaluation service not configured on app state")
    return svc


router = APIRouter(prefix="/api/evaluation", tags=["evaluation"])


@router.post("/run")
async def run_evaluation(
    req: EvaluationRequest,
    service: EvaluationService = Depends(get_evaluation),
) -> dict[str, object]:
    try:
        report = await service.run(
            backtest_id=req.backtest_id, model_id=req.model_id
        )
    except ModelNotFound as e:
        raise HTTPException(
            status_code=404,
            detail={
                "data": None,
                "error": {"code": "not_found", "message": str(e)},
            },
        )
    except BacktestNotFound as e:
        raise HTTPException(
            status_code=404,
            detail={
                "data": None,
                "error": {
                    "code": "not_found",
                    "message": f"backtest {e} not found",
                },
            },
        )
    except BackendError as e:
        raise HTTPException(
            status_code=502,
            detail={
                "data": None,
                "error": {"code": "upstream_unavailable", "message": str(e)},
            },
        )
    return {"data": report.model_dump(mode="json"), "error": None}


@router.get("/{evaluation_id}")
async def get_evaluation_report(
    evaluation_id: str,
    service: EvaluationService = Depends(get_evaluation),
) -> dict[str, object]:
    try:
        report = service.get(evaluation_id)
    except EvaluationNotFound:
        raise HTTPException(
            status_code=404,
            detail={
                "data": None,
                "error": {
                    "code": "not_found",
                    "message": f"evaluation {evaluation_id} not found",
                },
            },
        )
    return {"data": report.model_dump(mode="json"), "error": None}
