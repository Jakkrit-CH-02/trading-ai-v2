from __future__ import annotations

import logging
from decimal import Decimal
from typing import TypedDict

import httpx

log = logging.getLogger(__name__)


class BarRow(TypedDict):
    symbol: str
    interval: str
    open_time: int
    close_time: int
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal


class BackendError(RuntimeError):
    """Raised when the Go backend is unavailable or returns an error."""


class BackendClient:
    """Thin async client over the Go backend market data API.

    The backend's `/api/market/candles` endpoint takes `symbol`, `interval`,
    `limit` (max 1000) and returns the most recent bars. To honour an
    arbitrary `[from_ms, to_ms)` window we page by repeatedly fetching and
    filtering — the backend will gain a range query later, but until then
    a single page covers up to 1000 bars which is enough for unit tests
    and small datasets.
    """

    MAX_LIMIT = 1000

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def fetch_bars(
        self,
        *,
        symbol: str,
        interval: str,
        from_ms: int,
        to_ms: int,
        limit: int | None = None,
    ) -> list[BarRow]:
        params: dict[str, str | int] = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit or self.MAX_LIMIT, self.MAX_LIMIT),
        }
        try:
            resp = await self._client.get("/api/market/candles", params=params)
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendError(f"backend candles fetch failed: {e}") from e

        body = resp.json()
        bars_raw = body.get("bars") or body.get("data", {}).get("bars") or []
        out: list[BarRow] = []
        for b in bars_raw:
            ot = int(b["open_time"])
            if ot < from_ms or ot >= to_ms:
                continue
            out.append(
                BarRow(
                    symbol=str(b["symbol"]),
                    interval=str(b["interval"]),
                    open_time=ot,
                    close_time=int(b["close_time"]),
                    open=Decimal(str(b["open"])),
                    high=Decimal(str(b["high"])),
                    low=Decimal(str(b["low"])),
                    close=Decimal(str(b["close"])),
                    volume=Decimal(str(b["volume"])),
                )
            )
        out.sort(key=lambda r: r["open_time"])
        return out

    async def fetch_backtest(self, backtest_id: str) -> dict:
        """Fetch a single backtest result by id.

        Unwraps the standard `{data, error}` envelope and returns the inner
        result dict (config, metrics, equity_curve, trades, ...).
        """
        try:
            resp = await self._client.get(f"/api/backtest/{backtest_id}")
            resp.raise_for_status()
        except httpx.HTTPError as e:
            raise BackendError(f"backend backtest fetch failed: {e}") from e
        body = resp.json()
        if isinstance(body, dict) and "data" in body:
            err = body.get("error")
            if err:
                raise BackendError(f"backend returned error: {err}")
            return body["data"] or {}
        return body
