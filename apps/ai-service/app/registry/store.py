from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

import joblib

from .schemas import ActiveModels, Environment, ModelMetadata


class ModelNotFound(Exception):
    pass


class NotEvaluated(Exception):
    pass


def _model_id() -> str:
    return f"{int(time.time() * 1000):013x}{secrets.token_hex(4)}"


class ModelStore:
    """Filesystem-backed model registry.

    Layout:
        {root}/
            _active.json                # {"paper": id, "live": id}
            {model_id}/
                metadata.json
                model.joblib
    """

    METADATA_NAME = "metadata.json"
    ARTIFACT_NAME = "model.joblib"
    ACTIVE_NAME = "_active.json"

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    @property
    def root(self) -> Path:
        return self._root

    def _model_dir(self, model_id: str) -> Path:
        return self._root / model_id

    def _active_path(self) -> Path:
        return self._root / self.ACTIVE_NAME

    def save(
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
        mid = model_id or _model_id()
        version = self._next_version()
        out_dir = self._model_dir(mid)
        out_dir.mkdir(parents=True, exist_ok=True)
        artifact = out_dir / self.ARTIFACT_NAME
        joblib.dump(estimator, artifact)

        meta = ModelMetadata(
            id=mid,
            version=version,
            dataset_id=dataset_id,
            feature_schema_id=feature_schema_id,
            feature_names=list(feature_names or []),
            metrics=dict(metrics or {}),
            artifact_path=str(artifact),
            created_at_ms=int(time.time() * 1000),
            evaluated=evaluated,
        )
        (out_dir / self.METADATA_NAME).write_text(meta.model_dump_json())
        return meta

    def list(self) -> list[ModelMetadata]:
        out: list[ModelMetadata] = []
        if not self._root.exists():
            return out
        for child in self._root.iterdir():
            if not child.is_dir():
                continue
            meta_path = child / self.METADATA_NAME
            if not meta_path.exists():
                continue
            try:
                out.append(ModelMetadata.model_validate_json(meta_path.read_text()))
            except Exception:
                # Skip directories whose metadata.json predates this schema
                # (e.g. raw training-job artifacts written under the same root).
                continue
        out.sort(key=lambda m: m.version)
        return out

    def get(self, model_id: str) -> ModelMetadata:
        meta_path = self._model_dir(model_id) / self.METADATA_NAME
        if not meta_path.exists():
            raise ModelNotFound(model_id)
        return ModelMetadata.model_validate_json(meta_path.read_text())

    def update(self, meta: ModelMetadata) -> None:
        path = self._model_dir(meta.id) / self.METADATA_NAME
        if not path.exists():
            raise ModelNotFound(meta.id)
        path.write_text(meta.model_dump_json())

    def load_artifact(self, model_id: str) -> Any:
        meta = self.get(model_id)
        return joblib.load(meta.artifact_path)

    def active(self) -> ActiveModels:
        path = self._active_path()
        if not path.exists():
            return ActiveModels()
        return ActiveModels.model_validate_json(path.read_text())

    def set_active(self, environment: Environment, model_id: str) -> ActiveModels:
        # Ensure the model exists.
        self.get(model_id)
        current = self.active()
        data = current.model_dump()
        data[environment] = model_id
        updated = ActiveModels.model_validate(data)
        self._active_path().write_text(updated.model_dump_json())
        return updated

    def _next_version(self) -> int:
        existing = self.list()
        if not existing:
            return 1
        return max(m.version for m in existing) + 1
