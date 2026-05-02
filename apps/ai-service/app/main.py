import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.api.datasets import router as datasets_router
from app.api.features import router as features_router
from app.clients.backend import BackendClient
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.datasets.builder import DatasetBuilder
from app.features.service import FeatureService


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    settings = get_settings()
    log = logging.getLogger(__name__)
    log.info(
        "ai-service starting", extra={"env": settings.env, "port": settings.port}
    )

    async with httpx.AsyncClient(
        base_url=settings.backend_base_url,
        timeout=settings.backend_timeout_s,
    ) as http:
        app.state.http = http
        app.state.backend_client = BackendClient(http)
        app.state.dataset_builder = DatasetBuilder(
            backend=app.state.backend_client,
            root=Path("data/datasets"),
        )
        app.state.feature_service = FeatureService(
            builder=app.state.dataset_builder,
            root=Path("data/features"),
        )
        yield


app = FastAPI(title="ai-service", version="0.1.0", lifespan=lifespan)
app.include_router(datasets_router)
app.include_router(features_router)


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {
        "data": {"status": "ok", "model_loaded": False},
        "error": None,
    }
