from __future__ import annotations

import logging
from typing import Any

from .schemas import ActiveModels, Environment, ModelMetadata
from .store import ModelStore, NotEvaluated

log = logging.getLogger(__name__)


class RegistryService:
    """Coordinates model registration and environment promotion.

    Per the "Must-have before live trading" gate, promotion to `live`
    requires the model to have linked evaluation results
    (`metadata.evaluated == True`). Promotion to `paper` is unrestricted
    so operators can soak-test candidates before promotion.
    """

    def __init__(self, store: ModelStore) -> None:
        self._store = store

    @property
    def store(self) -> ModelStore:
        return self._store

    def register(
        self,
        *,
        estimator: Any,
        dataset_id: str,
        feature_schema_id: str | None = None,
        feature_names: list[str] | None = None,
        metrics: dict[str, float] | None = None,
        evaluated: bool = False,
        model_id: str | None = None,
    ) -> ModelMetadata:
        meta = self._store.save(
            estimator=estimator,
            dataset_id=dataset_id,
            feature_schema_id=feature_schema_id,
            feature_names=feature_names,
            metrics=metrics,
            evaluated=evaluated,
            model_id=model_id,
        )
        log.info(
            "model registered",
            extra={
                "model_id": meta.id,
                "version": meta.version,
                "dataset_id": meta.dataset_id,
            },
        )
        return meta

    def list(self) -> list[ModelMetadata]:
        return self._store.list()

    def get(self, model_id: str) -> ModelMetadata:
        return self._store.get(model_id)

    def active(self) -> ActiveModels:
        return self._store.active()

    def mark_evaluated(self, model_id: str, evaluated: bool = True) -> ModelMetadata:
        meta = self._store.get(model_id)
        meta.evaluated = evaluated
        self._store.update(meta)
        return meta

    def promote(self, model_id: str, environment: Environment) -> ActiveModels:
        meta = self._store.get(model_id)
        if environment == "live" and not meta.evaluated:
            raise NotEvaluated(
                f"model {model_id} is not evaluated; live promotion blocked"
            )
        active = self._store.set_active(environment, model_id)
        log.info(
            "model promoted",
            extra={
                "model_id": model_id,
                "environment": environment,
                "version": meta.version,
            },
        )
        return active
