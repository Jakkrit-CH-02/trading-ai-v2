from __future__ import annotations

import logging
import time
from pathlib import Path

import pandas as pd

from app.datasets.builder import DatasetBuilder

from .pipeline import compute_features
from .schemas import FeatureMetadata

log = logging.getLogger(__name__)


class DatasetNotFound(Exception):
    pass


class FeatureService:
    def __init__(self, *, builder: DatasetBuilder, root: Path) -> None:
        self._builder = builder
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def compute(
        self, dataset_id: str, features: list[str] | None = None
    ) -> FeatureMetadata:
        meta = next(
            (d for d in self._builder.list() if d.id == dataset_id), None
        )
        if meta is None:
            raise DatasetNotFound(dataset_id)

        df = pd.read_parquet(meta.path)
        feat = compute_features(df, features)

        out_path = self._root / f"{dataset_id}.parquet"
        feat.to_parquet(out_path, index=False)

        feature_cols = [c for c in feat.columns if c != "open_time"]
        result = FeatureMetadata(
            dataset_id=dataset_id,
            path=str(out_path),
            rows=len(feat),
            features=feature_cols,
            created_at_ms=int(time.time() * 1000),
        )
        log.info(
            "features computed",
            extra={
                "dataset_id": dataset_id,
                "rows": len(feat),
                "path": str(out_path),
            },
        )
        return result
