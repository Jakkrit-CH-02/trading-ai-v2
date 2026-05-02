from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.training.schemas import RunResponse, TrainRequest
from app.training.trainer import (
    DatasetNotFound,
    FeaturesNotFound,
    Trainer,
    TrainingError,
)


def get_trainer(request: Request) -> Trainer:
    t = getattr(request.app.state, "trainer", None)
    if t is None:  # pragma: no cover - lifespan wires this in main.py
        raise RuntimeError("trainer not configured on app state")
    return t


router = APIRouter(prefix="/api/training", tags=["training"])


@router.post("/run")
async def run_training(
    req: TrainRequest,
    trainer: Trainer = Depends(get_trainer),
) -> dict[str, object]:
    try:
        job = trainer.run(req)
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
    except FeaturesNotFound as e:
        raise HTTPException(
            status_code=404,
            detail={
                "data": None,
                "error": {
                    "code": "not_found",
                    "message": f"features parquet not found: {e}",
                },
            },
        )
    except TrainingError as e:
        raise HTTPException(
            status_code=400,
            detail={
                "data": None,
                "error": {"code": "validation_failed", "message": str(e)},
            },
        )

    if job.status == "failed":
        return {
            "data": RunResponse(job=job).model_dump(mode="json"),
            "error": {"code": "training_failed", "message": job.error or "unknown"},
        }
    return {
        "data": RunResponse(job=job).model_dump(mode="json"),
        "error": None,
    }


@router.get("/{job_id}")
async def get_training_job(
    job_id: str,
    trainer: Trainer = Depends(get_trainer),
) -> dict[str, object]:
    job = trainer.get(job_id)
    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "data": None,
                "error": {
                    "code": "not_found",
                    "message": f"training job {job_id} not found",
                },
            },
        )
    return {
        "data": RunResponse(job=job).model_dump(mode="json"),
        "error": None,
    }
