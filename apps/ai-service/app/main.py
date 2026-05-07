import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import FastAPI

from app.api.datasets import router as datasets_router
from app.api.evaluation import router as evaluation_router
from app.api.features import router as features_router
from app.api.models import router as models_router
from app.api.predict import router as predict_router
from app.api.training import router as training_router
from app.clients.backend import BackendClient
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.datasets.builder import DatasetBuilder
from app.evaluation.service import EvaluationService
from app.features.service import FeatureService
from app.inference.service import InferenceService
from app.registry.service import RegistryService
from app.registry.store import ModelStore
from app.training.trainer import Trainer


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
        app.state.registry = RegistryService(
            store=ModelStore(root=Path("data/models")),
        )
        app.state.trainer = Trainer(
            builder=app.state.dataset_builder,
            features_root=Path("data/features"),
            models_root=Path("data/models"),
            registry=app.state.registry,
        )
        app.state.inference = InferenceService(registry=app.state.registry)
        app.state.evaluation = EvaluationService(
            backend=app.state.backend_client,
            registry=app.state.registry,
        )
        try:
            app.state.inference.load()
        except Exception as e:
            log.warning(
                "inference load failed at startup",
                extra={"err": str(e)},
            )
        yield


app = FastAPI(title="ai-service", version="0.1.0", lifespan=lifespan)
app.include_router(datasets_router)
app.include_router(features_router)
app.include_router(training_router)
app.include_router(models_router)
app.include_router(predict_router)
app.include_router(evaluation_router)


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {
        "data": {"status": "ok", "model_loaded": False},
        "error": None,
    }
