from __future__ import annotations

import json
from pathlib import Path

import httpx
import pandas as pd
import pytest

from app.clients.backend import BackendClient
from app.datasets.builder import PARQUET_COLUMNS, DatasetBuilder
from app.datasets.schemas import BuildRequest


def _fake_bars(n: int, *, start_ms: int = 1_700_000_000_000, step_ms: int = 60_000):
    bars = []
    for i in range(n):
        ot = start_ms + i * step_ms
        price = 100 + i * 0.5
        bars.append(
            {
                "symbol": "BTCUSDT",
                "interval": "1m",
                "open_time": ot,
                "close_time": ot + step_ms - 1,
                "open": f"{price:.8f}",
                "high": f"{price + 0.25:.8f}",
                "low": f"{price - 0.25:.8f}",
                "close": f"{price + 0.10:.8f}",
                "volume": "1.50000000",
            }
        )
    return bars


def _make_transport(n_bars: int):
    bars = _fake_bars(n_bars)

    def handler(req: httpx.Request) -> httpx.Response:
        assert req.url.path == "/api/market/candles"
        assert req.url.params["symbol"] == "BTCUSDT"
        assert req.url.params["interval"] == "1m"
        return httpx.Response(
            200,
            json={"symbol": "BTCUSDT", "interval": "1m", "bars": bars},
        )

    return httpx.MockTransport(handler), bars


@pytest.mark.asyncio
async def test_build_100_bar_dataset_writes_parquet(tmp_path: Path) -> None:
    transport, bars = _make_transport(100)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://backend"
    ) as http:
        builder = DatasetBuilder(backend=BackendClient(http), root=tmp_path)
        req = BuildRequest(
            symbol="BTCUSDT",
            timeframe="1m",
            from_ms=bars[0]["open_time"],
            to_ms=bars[-1]["open_time"] + 60_000,
        )
        meta = await builder.build(req)

    parquet_path = Path(meta.path)
    assert parquet_path.exists()
    assert parquet_path.name == f"BTCUSDT_1m_{req.from_ms}_{req.to_ms}.parquet"

    df = pd.read_parquet(parquet_path)
    assert list(df.columns) == PARQUET_COLUMNS
    # 100 bars in, 1-step horizon drops the tail row → 99 labelled rows.
    assert len(df) == 99
    assert meta.rows == 99
    assert df["open_time"].is_monotonic_increasing
    # Splits cover the full frame and are time-ordered.
    assert set(df["split"].unique()) <= {"train", "val", "test"}
    assert df["split"].iloc[0] == "train"
    assert df["split"].iloc[-1] == "test"
    # Money columns stay as strings (no float conversion).
    assert pd.api.types.is_string_dtype(df["close"])
    assert isinstance(df["close"].iloc[0], str)
    # Labels are 0/1 for next_direction (rising series → all 1s here).
    assert set(df["label"].dropna().unique()).issubset({0, 1})

    meta_path = parquet_path.with_suffix(".json")
    assert meta_path.exists()
    saved = json.loads(meta_path.read_text())
    assert saved["symbol"] == "BTCUSDT"
    assert saved["rows"] == 99


@pytest.mark.asyncio
async def test_list_returns_built_datasets(tmp_path: Path) -> None:
    transport, bars = _make_transport(50)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://backend"
    ) as http:
        builder = DatasetBuilder(backend=BackendClient(http), root=tmp_path)
        req = BuildRequest(
            symbol="BTCUSDT",
            timeframe="1m",
            from_ms=bars[0]["open_time"],
            to_ms=bars[-1]["open_time"] + 60_000,
        )
        await builder.build(req)

    listed = builder.list()
    assert len(listed) == 1
    assert listed[0].symbol == "BTCUSDT"
