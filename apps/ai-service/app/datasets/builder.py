from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import pandas as pd

from app.clients.backend import BackendClient, BarRow

from .schemas import (
    BuildRequest,
    DatasetMetadata,
    LabelConfig,
    SplitConfig,
)

log = logging.getLogger(__name__)

PARQUET_COLUMNS = [
    "open_time",
    "close_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "label",
    "split",
]


def _ulid_like() -> str:
    # Producer-generated lowercase id. ULID lib not yet a dep; ms-based
    # monotonic id with random suffix is sufficient for filename uniqueness.
    import secrets

    return f"{int(time.time() * 1000):013x}{secrets.token_hex(4)}"


def _bars_to_frame(bars: list[BarRow]) -> pd.DataFrame:
    if not bars:
        return pd.DataFrame(columns=PARQUET_COLUMNS)
    df = pd.DataFrame(bars)
    # Decimals → strings for parquet (money-as-string convention).
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(str)
    df["open_time"] = df["open_time"].astype("int64")
    df["close_time"] = df["close_time"].astype("int64")
    return df


def _add_labels(df: pd.DataFrame, cfg: LabelConfig) -> pd.DataFrame:
    """Compute labels with shifted future values, dropping the tail rows
    whose horizon falls outside the dataset to prevent leakage."""
    if df.empty:
        df["label"] = pd.Series(dtype="float64")
        return df

    close = df["close"].astype(float)
    future = close.shift(-cfg.horizon)
    ret = (future - close) / close

    match cfg.kind:
        case "next_direction":
            label = (future > close).astype("Int64")
        case "future_return":
            label = ret.astype("Float64")
        case "threshold_move":
            label = pd.Series(0, index=df.index, dtype="Int64")
            label[ret > cfg.threshold] = 1
            label[ret < -cfg.threshold] = -1

    df = df.copy()
    df["label"] = label
    # Drop rows where the horizon-shifted future is undefined (NaN). This
    # is the basic data-leakage / boundary guard.
    return df.iloc[: len(df) - cfg.horizon].reset_index(drop=True)


def _add_splits(df: pd.DataFrame, cfg: SplitConfig) -> pd.DataFrame:
    n = len(df)
    if n == 0:
        df["split"] = pd.Series(dtype="object")
        return df
    train_end = int(n * cfg.train)
    val_end = train_end + int(n * cfg.val)
    splits = ["train"] * train_end + ["val"] * (val_end - train_end)
    splits += ["test"] * (n - len(splits))
    df = df.copy()
    df["split"] = splits
    return df


class DatasetBuilder:
    def __init__(self, *, backend: BackendClient, root: Path) -> None:
        self._backend = backend
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _filename(self, req: BuildRequest) -> str:
        return f"{req.symbol}_{req.timeframe}_{req.from_ms}_{req.to_ms}"

    async def build(self, req: BuildRequest) -> DatasetMetadata:
        bars = await self._backend.fetch_bars(
            symbol=req.symbol,
            interval=req.timeframe,
            from_ms=req.from_ms,
            to_ms=req.to_ms,
        )
        df = _bars_to_frame(bars)
        df = _add_labels(df, req.label)
        df = _add_splits(df, req.split)
        df = df[PARQUET_COLUMNS]

        stem = self._filename(req)
        parquet_path = self._root / f"{stem}.parquet"
        meta_path = self._root / f"{stem}.json"
        df.to_parquet(parquet_path, index=False)

        meta = DatasetMetadata(
            id=_ulid_like(),
            symbol=req.symbol,
            timeframe=req.timeframe,
            from_ms=req.from_ms,
            to_ms=req.to_ms,
            rows=len(df),
            label=req.label,
            split=req.split,
            path=str(parquet_path),
            created_at_ms=int(time.time() * 1000),
        )
        meta_path.write_text(meta.model_dump_json())
        log.info(
            "dataset built",
            extra={
                "symbol": req.symbol,
                "rows": len(df),
                "path": str(parquet_path),
            },
        )
        return meta

    def list(self) -> list[DatasetMetadata]:
        out: list[DatasetMetadata] = []
        for meta_file in sorted(self._root.glob("*.json")):
            try:
                out.append(DatasetMetadata.model_validate_json(meta_file.read_text()))
            except Exception as e:  # noqa: BLE001
                log.warning(
                    "skip unreadable metadata",
                    extra={"path": str(meta_file), "err": str(e)},
                )
        return out
