import asyncio
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.schemas import Sentiment, Ticker
from app.api.services import BinanceMarketGateway, Services
from app.auth.core import make_token
from app.core.config import Settings
from app.core.models import Side
from app.exchange.fake import FakeTradingExchange
from app.exchange.orders import OrderType
from app.main import create_app
from app.marketdata.store import InMemoryCandleStore
from app.risk import CircuitBreakers
from tests.helpers import make_kline

D = Decimal


def authed(app: FastAPI) -> TestClient:
    c = TestClient(app)
    secret = app.state.services.settings.jwt_secret.get_secret_value()
    c.headers["Authorization"] = "Bearer " + make_token(secret, uuid4(), "t@example.com", "access")
    return c


class FakeMarket:
    def __init__(self) -> None:
        self.calls = 0
        self.fng: Sentiment | None = Sentiment(value=68, label="Greed")

    async def tickers(self, symbols: list[str]) -> dict[str, Ticker]:
        self.calls += 1
        return {
            s: Ticker(
                symbol=s,
                last=D("100.5"),
                change24h_pct=D("1.25"),
                high=D(110),
                low=D(90),
                volume=D(1000),
            )
            for s in symbols
        }

    async def fear_greed(self) -> Sentiment | None:
        return self.fng

    async def aclose(self) -> None:
        pass


def make_services(trading: FakeTradingExchange | None = None, hours: int = 60) -> Services:
    store = InMemoryCandleStore()
    now = datetime.now(UTC).replace(minute=0, second=0, microsecond=0)
    ks = [replace(make_kline(i), open_time=now - timedelta(hours=hours - i)) for i in range(hours)]
    asyncio.run(store.save(ks))
    return Services(
        settings=Settings(symbols=["BTCUSDT", "ETHUSDT"], jwt_secret=SecretStr("k" * 40)),
        candles=store,
        market=FakeMarket(),
        trading=trading,
    )


@pytest.fixture
def client() -> TestClient:
    return authed(create_app(make_services()))


def test_candles_returns_the_newest_n_ascending_and_validates_input(client: TestClient) -> None:
    rows = client.get("/api/v1/markets/BTCUSDT/candles?interval=1h&limit=5").json()
    assert len(rows) == 5
    assert [r["time"] for r in rows] == sorted(r["time"] for r in rows)
    assert rows[-1]["close"] == 100 + 59 + 0.5  # make_kline(59): price 159, close +0.5
    assert client.get("/api/v1/markets/XXXUSDT/candles").status_code == 404
    assert client.get("/api/v1/markets/BTCUSDT/candles?limit=0").status_code == 422
    assert client.get("/api/v1/markets/BTCUSDT/candles?interval=2h").status_code == 422


def test_daily_candles_are_aggregated_from_hourly() -> None:
    svc = make_services(hours=72)
    r = authed(create_app(svc)).get("/api/v1/markets/BTCUSDT/candles?interval=1d&limit=10")
    assert r.status_code == 200
    rows = r.json()
    assert rows and all(c["high"] >= c["low"] for c in rows)
    assert all(rows[i]["time"] < rows[i + 1]["time"] for i in range(len(rows) - 1))


def test_stats_watchlist_and_sentiment(client: TestClient) -> None:
    st = client.get("/api/v1/markets/BTCUSDT/stats").json()
    assert st["last"] == "100.5" and st["funding_rate"] is None
    wl = client.get("/api/v1/watchlist").json()
    assert [w["symbol"] for w in wl] == ["BTCUSDT", "ETHUSDT"]
    assert wl[0]["name"] == "Bitcoin"
    assert client.get("/api/v1/sentiment").json()["value"] == 68


def test_sentiment_unavailable_is_a_502() -> None:
    svc = make_services()
    svc.market.fng = None  # type: ignore[attr-defined]
    assert authed(create_app(svc)).get("/api/v1/sentiment").status_code == 502


def test_summary_without_account_is_not_connected(client: TestClient) -> None:
    j = client.get("/api/v1/dashboard/summary").json()
    assert j["connected"] is False and j["allocation"] == []
    assert client.get("/api/v1/orders").json() == []


async def _trading() -> FakeTradingExchange:
    ex = FakeTradingExchange({"BTCUSDT": D(100)}, free={"USDT": D(1000), "BTC": D(5)})
    await ex.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "cid-1", price=D(90))
    return ex


def test_summary_and_orders_with_an_account() -> None:
    ex = asyncio.run(_trading())
    svc = make_services(ex)
    c = authed(create_app(svc))
    j = c.get("/api/v1/dashboard/summary").json()
    # buy 1 BTC @90 locks 90.09 (incl. 0.1% fee); BTC is quoted at 100.5 by the fake market
    assert j["connected"] is True and j["mode"] == "paper"
    assert D(j["available"]) == D("909.91") and D(j["in_orders"]) == D("90.09")
    assert D(j["equity"]) == D("1502.5")  # 909.91 + 90.09 + 5 x 100.5
    assert j["pnl_today"] is not None and D(j["pnl_today"]) == 0  # first observation of the day
    assert j["allocation"] == [{"label": "BTC", "pct": 33}, {"label": "Cash", "pct": 67}]
    o = c.get("/api/v1/orders?status=open").json()
    assert (
        len(o) == 1 and o[0]["id"] == "cid-1" and o[0]["side"] == "BUY" and o[0]["status"] == "NEW"
    )
    assert c.get("/api/v1/orders?status=filled").json() == []


def test_bots_and_risk_status_defaults_and_active_breaker() -> None:
    svc = make_services()
    c = authed(create_app(svc))
    assert c.get("/api/v1/bots/summary").json()["running"] == 0
    r = c.get("/api/v1/risk/status").json()
    assert r["kill_switch"] is False and r["breakers"] == [] and r["open_risk_cap_pct"] == "2.00"
    b = CircuitBreakers(svc.profile)
    b.trigger_kill(datetime.now(UTC), "manual")
    svc.breakers = b
    r = c.get("/api/v1/risk/status").json()
    assert r["kill_switch"] is True and r["entries_blocked"] is True
    assert r["breakers"][0]["kind"] == "KILL_SWITCH"


def test_websocket_pushes_ticker_and_risk_then_stops_on_unsubscribe(client: TestClient) -> None:
    token = client.headers["Authorization"][7:]
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"op": "auth", "token": token}))
        ws.send_text(json.dumps({"op": "subscribe", "channels": ["ticker:BTCUSDT", "risk"]}))
        seen: dict[str, dict[str, Any]] = {}
        while len(seen) < 2:
            m = json.loads(ws.receive_text())
            seen[m["ch"]] = m
        assert seen["ticker:BTCUSDT"]["data"]["last"] == "100.5"
        assert seen["risk"]["data"]["kill_switch"] is False
        assert isinstance(seen["risk"]["ts"], int)
        ws.send_text("not json")
        while (m := json.loads(ws.receive_text()))["ch"] != "error":
            pass
        assert m["data"]["error"] == "bad json"


async def test_gateway_parses_binance_and_caches_for_a_second() -> None:
    hits = {"t": 0, "f": 0}

    def handler(req: httpx.Request) -> httpx.Response:
        if "ticker/24hr" in req.url.path:
            hits["t"] += 1
            return httpx.Response(
                200,
                json=[
                    {
                        "symbol": "BTCUSDT",
                        "lastPrice": "97412.50",
                        "priceChangePercent": "2.84",
                        "highPrice": "98120",
                        "lowPrice": "94305.4",
                        "volume": "32800",
                    }
                ],
            )
        hits["f"] += 1
        return httpx.Response(
            200,
            json={
                "data": [
                    {"value": "68", "value_classification": "Greed", "timestamp": "1700000000"}
                ]
            },
        )

    gw = BinanceMarketGateway(
        "https://x.test",
        "https://fng.test/fng/",
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    t = (await gw.tickers(["BTCUSDT"]))["BTCUSDT"]
    assert t.last == D("97412.50") and t.change24h_pct == D("2.84")
    await gw.tickers(["BTCUSDT"])
    assert hits["t"] == 1  # second call served from the 1 s cache
    s = await gw.fear_greed()
    assert s is not None and s.value == 68 and s.label == "Greed"
    await gw.fear_greed()
    assert hits["f"] == 1
    await gw.aclose()


async def test_gateway_keeps_last_sentiment_when_the_source_fails() -> None:
    ok = {"v": True}

    def handler(req: httpx.Request) -> httpx.Response:
        if ok["v"]:
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "value": "10",
                            "value_classification": "Extreme Fear",
                            "timestamp": "1700000000",
                        }
                    ]
                },
            )
        return httpx.Response(500)

    gw = BinanceMarketGateway(
        "https://x.test",
        "https://fng.test/",
        httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    first = await gw.fear_greed()
    assert first is not None
    ok["v"] = False
    gw._fng = (0.0, first)  # expire the cache
    assert await gw.fear_greed() == first


def test_every_v1_endpoint_requires_a_valid_access_token() -> None:
    app = create_app(make_services())
    anon = TestClient(app)
    for path in (
        "/api/v1/dashboard/summary",
        "/api/v1/watchlist",
        "/api/v1/orders",
        "/api/v1/bots",
    ):
        assert anon.get(path).status_code == 401
    assert anon.get("/api/v1/bots", headers={"Authorization": "Bearer junk"}).status_code == 401
    secret = app.state.services.settings.jwt_secret.get_secret_value()
    refresh = make_token(secret, uuid4(), "t@example.com", "refresh")
    assert (
        anon.get("/api/v1/bots", headers={"Authorization": f"Bearer {refresh}"}).status_code == 401
    )
    assert anon.get("/health").status_code == 200  # liveness stays public


def test_websocket_rejects_unauthenticated_clients(client: TestClient) -> None:
    anon = TestClient(client.app)
    with anon.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"op": "subscribe", "channels": ["risk"]}))
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_text()
        assert e.value.code == 4401
