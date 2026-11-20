"""Shared dependencies of the HTTP/WS layer. Everything external is behind a small interface
so the API can be tested without a network, a database or an exchange."""

import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, Protocol

import httpx
from fastapi import Request

from app.api.schemas import Sentiment, Ticker
from app.core.config import Settings
from app.exchange.trading import TradingAdapter
from app.marketdata.store import CandleStore
from app.risk import CircuitBreakers, RiskProfile

NAMES = {
    "BTCUSDT": "Bitcoin",
    "ETHUSDT": "Ethereum",
    "SOLUSDT": "Solana",
    "BNBUSDT": "BNB",
    "XRPUSDT": "XRP",
}


class MarketGateway(Protocol):
    async def tickers(self, symbols: list[str]) -> dict[str, Ticker]: ...

    async def fear_greed(self) -> Sentiment | None: ...

    async def aclose(self) -> None: ...


class BinanceMarketGateway:
    """Public Binance REST (24h tickers, 1 s cache) + the public Fear & Greed index (1 h cache)."""

    def __init__(
        self, rest_url: str, fng_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._rest = rest_url.rstrip("/")
        self._fng_url = fng_url
        self._http = client or httpx.AsyncClient(timeout=5.0)
        self._tick: tuple[float, dict[str, Ticker]] = (0.0, {})
        self._fng: tuple[float, Sentiment | None] = (0.0, None)

    async def tickers(self, symbols: list[str]) -> dict[str, Ticker]:
        now = time.monotonic()
        stamp, cached = self._tick
        if now - stamp < 1.0 and all(s in cached for s in symbols):
            return {s: cached[s] for s in symbols}
        import json

        res = await self._http.get(
            f"{self._rest}/api/v3/ticker/24hr",
            params={"symbols": json.dumps(symbols, separators=(",", ":"))},
        )
        res.raise_for_status()
        out = {
            r["symbol"]: Ticker(
                symbol=r["symbol"],
                last=Decimal(r["lastPrice"]),
                change24h_pct=Decimal(r["priceChangePercent"]),
                high=Decimal(r["highPrice"]),
                low=Decimal(r["lowPrice"]),
                volume=Decimal(r["volume"]),
            )
            for r in res.json()
        }
        self._tick = (now, out)
        return {s: out[s] for s in symbols if s in out}

    async def fear_greed(self) -> Sentiment | None:
        now = time.monotonic()
        stamp, cached = self._fng
        if cached is not None and now - stamp < 3600:
            return cached
        try:
            res = await self._http.get(self._fng_url, params={"limit": 1})
            res.raise_for_status()
            d = res.json()["data"][0]
            val = Sentiment(
                value=int(d["value"]),
                label=str(d["value_classification"]),
                updated=datetime.fromtimestamp(int(d["timestamp"]), tz=UTC),
            )
        except (httpx.HTTPError, KeyError, ValueError, IndexError):
            return cached  # keep serving the last good value; None when never fetched
        self._fng = (now, val)
        return val

    async def aclose(self) -> None:
        await self._http.aclose()


@dataclass
class DayStart:
    """First equity observed on each UTC day. In-memory: resets on restart (documented
    approximation until the equity-snapshot table exists)."""

    day: date | None = None
    equity: Decimal | None = None

    def pnl(self, equity: Decimal, now: datetime) -> tuple[Decimal, Decimal | None]:
        today = now.astimezone(UTC).date()
        if self.day != today or self.equity is None:
            self.day, self.equity = today, equity
        diff = equity - self.equity
        return diff, (diff / self.equity * 100 if self.equity else None)


@dataclass
class Services:
    settings: Settings
    candles: CandleStore
    market: MarketGateway
    trading: TradingAdapter | None = None
    profile: RiskProfile = field(default_factory=RiskProfile)
    breakers: CircuitBreakers | None = None
    day_start: DayStart = field(default_factory=DayStart)
    extras: dict[str, Any] = field(default_factory=dict)

    def risk_breakers(self) -> CircuitBreakers:
        if self.breakers is None:
            self.breakers = CircuitBreakers(self.profile)
        return self.breakers


def get_services(request: Request) -> Services:
    services: Services = request.app.state.services
    return services
