"""Binance Spot public market data (read-only, no API key).

Defaults point at Binance's market-data-only hosts, which serve public data and
cannot place orders. Use the testnet URLs for paper trading in Phase 3.
"""

import asyncio
import json
from collections.abc import AsyncIterator, Sequence
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import structlog
import websockets

from app.exchange.base import ExchangeAdapter
from app.exchange.errors import ExchangeError, IPBanned, RateLimited
from app.exchange.ratelimit import WeightTracker
from app.exchange.types import BookTicker, Kline, MarketEvent, dt_to_ms, ms_to_dt

log = structlog.get_logger()

MAINNET_DATA_REST = "https://data-api.binance.vision"
MAINNET_DATA_WS = "wss://data-stream.binance.vision"
TESTNET_REST = "https://testnet.binance.vision"
TESTNET_WS = "wss://stream.testnet.binance.vision"

MAX_WS_LIFETIME_S = 23 * 3600  # reconnect before Binance's 24h cutoff


def parse_rest_kline(symbol: str, interval: str, row: list[Any], now_ms: int) -> Kline:
    """REST row: [openT, o, h, l, c, v, closeT, quoteV, trades, takerBuyBase, takerBuyQuote, _]."""
    return Kline(
        symbol=symbol,
        interval=interval,
        open_time=ms_to_dt(int(row[0])),
        o=Decimal(row[1]),
        h=Decimal(row[2]),
        l=Decimal(row[3]),
        c=Decimal(row[4]),
        v=Decimal(row[5]),
        quote_v=Decimal(row[7]),
        trades=int(row[8]),
        taker_buy_v=Decimal(row[9]),
        is_closed=int(row[6]) < now_ms,
    )


def parse_ws_message(raw: str | bytes, received_at: datetime | None = None) -> MarketEvent | None:
    """Parse a combined-stream frame. Returns None for frames we do not use."""
    msg = json.loads(raw)
    data = msg.get("data", msg)
    if data.get("e") == "kline":
        k = data["k"]
        return Kline(
            symbol=k["s"],
            interval=k["i"],
            open_time=ms_to_dt(int(k["t"])),
            o=Decimal(k["o"]),
            h=Decimal(k["h"]),
            l=Decimal(k["l"]),
            c=Decimal(k["c"]),
            v=Decimal(k["v"]),
            quote_v=Decimal(k["q"]),
            trades=int(k["n"]),
            taker_buy_v=Decimal(k["V"]),
            is_closed=bool(k["x"]),
        )
    if "b" in data and "a" in data and "s" in data:
        return BookTicker(
            symbol=data["s"],
            bid=Decimal(data["b"]),
            bid_qty=Decimal(data["B"]),
            ask=Decimal(data["a"]),
            ask_qty=Decimal(data["A"]),
            ts=received_at or datetime.now(UTC),
        )
    return None


class BinancePublicAdapter(ExchangeAdapter):
    def __init__(
        self,
        rest_url: str = MAINNET_DATA_REST,
        ws_url: str = MAINNET_DATA_WS,
        client: httpx.AsyncClient | None = None,
        weights: WeightTracker | None = None,
    ) -> None:
        self._rest_url = rest_url.rstrip("/")
        self._ws_url = ws_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self.weights = weights or WeightTracker()

    async def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        await self.weights.wait_if_needed()
        res = await self._client.get(f"{self._rest_url}{path}", params=params)
        self.weights.update_from_headers(res.headers)
        retry_after = float(res.headers.get("retry-after", "60"))
        if res.status_code == 418:
            raise IPBanned(retry_after)
        if res.status_code == 429:
            raise RateLimited(retry_after)
        if res.status_code >= 400:
            raise ExchangeError(f"GET {path} failed: {res.status_code} {res.text[:200]}")
        return res.json()

    async def server_time(self) -> datetime:
        data = await self._get("/api/v3/time")
        return ms_to_dt(int(data["serverTime"]))

    async def get_klines(
        self,
        symbol: str,
        interval: str,
        start: datetime | None = None,
        end: datetime | None = None,
        limit: int = 1000,
    ) -> list[Kline]:
        params: dict[str, Any] = {"symbol": symbol, "interval": interval, "limit": min(limit, 1000)}
        if start is not None:
            params["startTime"] = dt_to_ms(start)
        if end is not None:
            params["endTime"] = dt_to_ms(end)
        rows = await self._get("/api/v3/klines", params)
        now_ms = dt_to_ms(await self.server_time()) if rows else 0
        klines = [parse_rest_kline(symbol, interval, r, now_ms) for r in rows]
        return [k for k in klines if k.is_closed]  # never store a forming candle

    async def stream_market(
        self, symbols: Sequence[str], intervals: Sequence[str]
    ) -> AsyncIterator[MarketEvent]:
        streams = [f"{s.lower()}@bookTicker" for s in symbols]
        streams += [f"{s.lower()}@kline_{i}" for s in symbols for i in intervals]
        url = f"{self._ws_url}/stream?streams={'/'.join(streams)}"
        loop = asyncio.get_running_loop()
        started = loop.time()
        async with websockets.connect(url, ping_interval=20, max_size=2**20) as ws:
            log.info("ws.connected", streams=len(streams))
            async for raw in ws:
                event = parse_ws_message(raw)
                if event is not None:
                    yield event
                if loop.time() - started > MAX_WS_LIFETIME_S:
                    log.info("ws.rotating", reason="24h limit")
                    return

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
