from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from app.datasets.builder import DatasetBuilder
from app.datasets.schemas import BuildRequest, BuildResponse, ListResponse


def get_builder(request: Request) -> DatasetBuilder:
    builder = getattr(request.app.state, "dataset_builder", None)
    if builder is None:  # pragma: no cover - lifespan wires this in main.py
        raise RuntimeError("dataset_builder not configured on app state")
    return builder


router = APIRouter(prefix="/api/datasets", tags=["datasets"])


@router.post("/build")
async def build_dataset(
    req: BuildRequest,
    builder: DatasetBuilder = Depends(get_builder),
) -> dict[str, object]:
    meta = await builder.build(req)
    return {"data": BuildResponse(dataset=meta).model_dump(mode="json"), "error": None}


@router.get("")
async def list_datasets(
    builder: DatasetBuilder = Depends(get_builder),
) -> dict[str, object]:
    items = builder.list()
    return {
        "data": ListResponse(datasets=items).model_dump(mode="json"),
        "error": None,
    }
