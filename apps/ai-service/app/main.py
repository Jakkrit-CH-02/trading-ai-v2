import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import get_settings
from app.core.logging import setup_logging


@asynccontextmanager
async def lifespan(_: FastAPI):
    setup_logging()
    settings = get_settings()
    logging.getLogger(__name__).info(
        "ai-service starting", extra={"env": settings.env, "port": settings.port}
    )
    yield


app = FastAPI(title="ai-service", version="0.1.0", lifespan=lifespan)


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {
        "data": {"status": "ok", "model_loaded": False},
        "error": None,
    }
