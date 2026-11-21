"""Manual orders must go through the Risk Engine exactly like bot orders."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.api.services import Services
from app.auth.core import make_token
from app.auth.crypto import generate_master_key
from app.auth.routes import create_user
from app.core.config import Settings
from app.core.db import make_session_factory
from app.core.models import AuditLog, Side
from app.exchange.fake import FakeTradingExchange
from app.exchange.orders import OrderType
from app.execution import PgExecutionStore
from app.main import create_app
from tests.conftest import needs_pg
from tests.test_api import authed, make_services

D = Decimal


def account() -> FakeTradingExchange:
    return FakeTradingExchange(
        {"BTCUSDT": D("100.5"), "ETHUSDT": D("100.5")}, free={"USDT": D(10_000)}
    )


def client(ex: FakeTradingExchange | None = None) -> tuple[TestClient, Services]:
    svc = make_services(ex)
    return authed(create_app(svc)), svc


GOOD = {"symbol": "BTCUSDT", "order_type": "LIMIT", "entry": "100", "stop": "95", "tp1": "115"}


def test_preview_sizes_the_order_from_risk_and_reports_risk_as_percent_of_equity() -> None:
    c, _ = client(account())
    r = c.post("/api/v1/orders/preview", json=GOOD)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["approved"] is True and D(j["qty"]) > 0 and j["reasons"] == []
    assert D("0.4") <= D(j["risk_pct_of_equity"]) <= D("0.5")  # profile: 0.5% per trade
    assert D(j["notional"]) <= D(10_000) * D("0.25")  # symbol exposure cap
    assert any(ch["name"] == "kill_switch" and ch["passed"] for ch in j["checks"])


@pytest.mark.parametrize(
    ("override", "reason"),
    [
        ({"tp1": "101"}, "RR_TOO_LOW"),
        ({"tp1": None}, "NO_TARGET"),
        ({"stop": "101"}, "BAD_STOP_SIDE"),
    ],
)
def test_preview_rejects_what_the_risk_engine_rejects(
    override: dict[str, Any], reason: str
) -> None:
    c, _ = client(account())
    j = c.post("/api/v1/orders/preview", json={**GOOD, **override}).json()
    assert j["approved"] is False and reason in j["reasons"] and D(j["qty"]) == 0


def test_an_active_kill_switch_blocks_manual_orders_too() -> None:
    c, svc = client(account())
    svc.risk_breakers().trigger_kill(datetime.now(UTC), "test")
    j = c.post("/api/v1/orders/preview", json=GOOD).json()
    assert j["approved"] is False and "KILL_SWITCH" in j["reasons"]


def test_input_validation_and_missing_account() -> None:
    c, _ = client(account())
    assert c.post("/api/v1/orders/preview", json={**GOOD, "symbol": "DOGEUSDT"}).status_code == 404
    assert c.post("/api/v1/orders/preview", json={**GOOD, "entry": None}).status_code == 422
    assert c.post("/api/v1/orders/preview", json={**GOOD, "stop": "0"}).status_code == 422
    assert c.post("/api/v1/orders/preview", json={"symbol": "BTCUSDT"}).status_code == 422
    no_account, _ = client(None)
    assert no_account.post("/api/v1/orders/preview", json=GOOD).status_code == 409
    anon = TestClient(c.app)
    assert anon.post("/api/v1/orders/preview", json=GOOD).status_code == 401


def test_depth_returns_both_sides() -> None:
    c, _ = client(account())
    j = c.get("/api/v1/markets/BTCUSDT/depth?limit=5").json()
    assert len(j["bids"]) == len(j["asks"]) == 5 and j["bids"][0]["price"] == "100"
    assert c.get("/api/v1/markets/BTCUSDT/depth?limit=1").status_code == 422


# ---- placing and cancelling (audit needs the database) ---------------------------------------


@pytest.fixture
async def pg(
    pg_engine: AsyncEngine,
) -> AsyncIterator[tuple[httpx.AsyncClient, Services, FakeTradingExchange]]:
    ex = await asyncio.to_thread(account)
    svc = await asyncio.to_thread(make_services, ex)
    svc.settings = Settings(
        _env_file=None,
        jwt_secret=SecretStr("k" * 40),
        master_key=SecretStr(generate_master_key()),
        symbols=["BTCUSDT", "ETHUSDT"],
    )
    svc.db = make_session_factory(pg_engine)
    svc.exec_store = PgExecutionStore(svc.db)  # the same wiring as production
    user, _ = await create_user(svc, "t@example.com", "pw-pw-pw-pw-pw")
    token = make_token("k" * 40, user.id, user.email, "access")
    transport = httpx.ASGITransport(app=create_app(svc))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers={"Authorization": f"Bearer {token}"}
    ) as c:
        yield c, svc, ex


async def actions(svc: Services) -> list[str]:
    assert svc.db
    async with svc.db() as s:
        return list((await s.execute(select(AuditLog.action).order_by(AuditLog.id))).scalars())


@needs_pg
async def test_a_market_order_is_sized_filled_and_gets_an_exchange_side_stop(
    pg: tuple[httpx.AsyncClient, Services, FakeTradingExchange],
) -> None:
    c, svc, ex = pg
    body = {"symbol": "BTCUSDT", "order_type": "MARKET", "stop": "95", "tp1": "115"}
    r = await c.post("/api/v1/orders", json=body)
    assert r.status_code == 201, r.text
    j = r.json()
    assert j["status"] == "PROTECTED", j
    assert j["client_order_id"] and j["preview"]["approved"]
    pos = await svc.exec_store.get_position("BTCUSDT")
    assert pos is not None and pos.protected and pos.stop <= D(95)
    assert ex.holding("BTC") > 0  # really bought on the (fake) exchange
    assert "order.place" in await actions(svc)
    again = (await c.post("/api/v1/orders", json=body)).json()
    assert (
        again["status"] == "REJECTED" and "already open" in again["detail"]
    )  # one position per symbol


@needs_pg
async def test_a_rejected_order_sends_nothing_to_the_exchange(
    pg: tuple[httpx.AsyncClient, Services, FakeTradingExchange],
) -> None:
    c, svc, ex = pg
    svc.risk_breakers().trigger_kill(datetime.now(UTC), "test")
    r = await c.post(
        "/api/v1/orders",
        json={"symbol": "BTCUSDT", "order_type": "MARKET", "stop": "95", "tp1": "115"},
    )
    assert r.status_code == 201 and r.json()["status"] == "REJECTED"
    assert "KILL_SWITCH" in r.json()["detail"]
    assert not any(call[0] == "place_order" for call in ex.calls)
    assert "order.rejected" in await actions(svc)


@needs_pg
async def test_cancel_removes_an_open_order_and_unknown_ids_404(
    pg: tuple[httpx.AsyncClient, Services, FakeTradingExchange],
) -> None:
    c, svc, ex = pg
    await ex.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "cid-1", price=D(90))
    assert (await c.delete("/api/v1/orders/cid-1?symbol=BTCUSDT")).status_code == 204
    assert await ex.open_orders() == []
    assert (await c.delete("/api/v1/orders/nope?symbol=BTCUSDT")).status_code == 404
    assert "order.cancel" in await actions(svc)


def test_walk_asks_reports_slippage_and_treats_a_thin_book_as_unfillable() -> None:
    from app.api.orders import walk_asks
    from app.api.schemas import DepthLevel

    book = [DepthLevel(price=D(100), qty=D(1)), DepthLevel(price=D(101), qty=D(1))]
    assert walk_asks(book, D(50)) == 0  # fits inside the best level
    assert walk_asks(book, D(150)) == pytest.approx(D("33.1"), abs=D("0.2"))  # 50 @100 + 100 @101
    assert walk_asks(book, D(500)) == D(10_000)  # more than the whole book
    assert walk_asks([], D(10)) == D(10_000)


@needs_pg
async def test_order_history_lists_every_leg_newest_first_and_survives_a_restart(
    pg: tuple[httpx.AsyncClient, Services, FakeTradingExchange],
) -> None:
    c, svc, _ = pg
    assert (await c.get("/api/v1/orders?status=history")).json() == []
    body = {"symbol": "BTCUSDT", "order_type": "MARKET", "stop": "95", "tp1": "115"}
    assert (await c.post("/api/v1/orders", json=body)).json()["status"] == "PROTECTED"
    rows = (await c.get("/api/v1/orders?status=history")).json()
    assert len(rows) == 4  # entry + OCO (stop, take-profit) + stop for the remainder
    assert {r["source"] for r in rows} == {"manual"} and {r["symbol"] for r in rows} == {"BTCUSDT"}
    assert [r["ts"] for r in rows] == sorted((r["ts"] for r in rows), reverse=True)
    entry = next(r for r in rows if r["type"] == "MARKET")
    assert entry["status"] == "FILLED" and D(entry["executed_qty"]) > 0
    filled = (await c.get("/api/v1/orders?status=filled")).json()
    assert [r["id"] for r in filled] == [entry["id"]]
    assert len((await c.get("/api/v1/orders?status=history&limit=2")).json()) == 2
    # a new process (new store object, same database) still sees the position and the history
    assert svc.db is not None
    again = await PgExecutionStore(svc.db).get_position("BTCUSDT")
    assert again is not None and again.protected
