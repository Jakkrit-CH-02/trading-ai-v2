"""PgExecutionStore: the same order-manager scenarios, but state lives in PostgreSQL.

The point is crash safety: a fresh store object over the same database (a restart) must see
exactly the position the old process left behind, including the stop/TP order ids.
"""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine

from app.core.db import make_session_factory
from app.core.models import Fill, Order, OrderLeg, PositionStatus, RiskEvent
from app.core.models import Position as PositionRow
from app.core.models import Trade as TradeRow
from app.exchange.orders import OrderStatus
from app.execution import ExecStatus, PgExecutionStore
from app.execution.pg_store import as_uuid, decode_position, encode_position
from tests.conftest import needs_pg
from tests.exec_helpers import Env, make_env

D = Decimal
pytestmark = needs_pg


def pg_env(engine: AsyncEngine) -> tuple[Env, PgExecutionStore]:
    env = make_env()
    store = PgExecutionStore(make_session_factory(engine))
    env.store = store  # type: ignore[assignment]
    env.mgr.store = store
    return env, store


async def count(engine: AsyncEngine, model: type) -> int:
    async with make_session_factory(engine)() as db:
        return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


def test_ids_that_are_not_uuids_are_stored_as_null() -> None:
    assert as_uuid("not-a-uuid") is None and as_uuid(None) is None and as_uuid("") is None
    assert as_uuid("12345678-1234-5678-1234-567812345678") is not None


async def test_position_survives_a_restart_with_every_field(pg_engine: AsyncEngine) -> None:
    env, _ = pg_env(pg_engine)
    r = await env.submit()
    assert r.status == ExecStatus.PROTECTED and r.position is not None

    restarted = PgExecutionStore(make_session_factory(pg_engine))  # a new process
    pos = await restarted.get_position("BTCUSDT")
    assert pos is not None and pos.protected and not pos.closed
    assert pos == r.position  # lossless: Decimals, datetimes, id lists
    assert pos.tp_cid and pos.stop_cids
    assert await restarted.open_positions() == [pos]
    assert decode_position(encode_position(pos)) == pos


async def test_every_leg_is_recorded_and_open_orders_are_rebuilt(pg_engine: AsyncEngine) -> None:
    env, store = pg_env(pg_engine)
    await env.submit()
    async with make_session_factory(pg_engine)() as db:
        legs = sorted(str(o.leg) for o in (await db.execute(select(Order))).scalars())
    assert legs == sorted([OrderLeg.ENTRY, OrderLeg.SL, OrderLeg.SL, OrderLeg.TP])
    open_now = await store.open_orders()
    exchange_open = {o.cid for o in env.ex.orders.values() if o.status.is_open}
    assert {o.client_order_id for o in open_now} == exchange_open
    assert all(o.status in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED) for o in open_now)
    assert await store.has_order(open_now[0].client_order_id)
    assert not await store.has_order("nope")


async def test_resubmitting_the_same_signal_is_still_a_duplicate_after_restart(
    pg_engine: AsyncEngine,
) -> None:
    env, _ = pg_env(pg_engine)
    await env.submit()
    again = await env.submit()  # idempotency is decided by the database, not by memory
    assert again.status in (ExecStatus.DUPLICATE, ExecStatus.REJECTED)
    assert await count(pg_engine, Order) == 4  # entry + OCO(stop, tp) + runner stop


async def test_tp1_then_stop_is_recorded_as_one_trade_with_fills(pg_engine: AsyncEngine) -> None:
    env, store = pg_env(pg_engine)
    await env.submit()
    env.ex.set_price("BTCUSDT", D(105))
    assert await env.mgr.sync_position("BTCUSDT") == ["TP1_FILLED", "STOP_MOVED_TO_BREAKEVEN"]
    pos = await store.get_position("BTCUSDT")
    assert pos is not None and pos.tp1_done and pos.stop == D("100.20")

    env.ex.set_price("BTCUSDT", D("100.1"))  # back down through the breakeven stop
    assert await env.mgr.sync_position("BTCUSDT") == ["CLOSED_STOP"]
    assert await store.get_position("BTCUSDT") is None
    assert await count(pg_engine, TradeRow) == 1
    assert await count(pg_engine, Fill) >= 2  # entry excluded; TP and stop fills
    async with make_session_factory(pg_engine)() as db:
        row = (await db.execute(select(PositionRow))).scalar_one()
        trade = (await db.execute(select(TradeRow))).scalar_one()
    assert row.status == PositionStatus.CLOSED and row.closed_at is not None
    assert trade.exit_reason == "stop" and trade.position_id == row.id


async def test_recording_the_same_order_or_trade_twice_changes_nothing(
    pg_engine: AsyncEngine,
) -> None:
    env, store = pg_env(pg_engine)
    r = await env.submit()
    assert r.position is not None
    info = next(iter(env.ex.orders.values()))
    before = await count(pg_engine, Order)
    await store.record_order(await env.ex.get_order("BTCUSDT", info.cid), "ENTRY", None, None)
    assert await count(pg_engine, Order) == before
    env.ex.set_price("BTCUSDT", D("97.9"))
    await env.mgr.sync_position("BTCUSDT")
    pos = r.position
    await store.record_trade(pos, D(1), D(1), D(0), "stop")  # a replayed close
    assert await count(pg_engine, TradeRow) == 1


async def test_risk_events_are_persisted(pg_engine: AsyncEngine) -> None:
    _, store = pg_env(pg_engine)
    await store.risk_event("X" * 80, "warning", {"a": 1})
    async with make_session_factory(pg_engine)() as db:
        types = [e.type for e in (await db.execute(select(RiskEvent))).scalars()]
    assert types == ["X" * 48]  # the column is 48 wide; never fail a safety write over length


def test_decode_ignores_unknown_keys_for_forward_compatibility() -> None:
    d = {"symbol": "BTCUSDT", "bot_id": None, "signal_id": None, "strategy": "manual"}
    d.update({"qty0": "1", "qty": "1", "avg_entry": "100", "stop": "95", "tp1": None})
    d.update({"entry_cid": "c", "opened_at": "2026-01-01T00:00:00+00:00", "future": "x"})
    p = decode_position(d)
    assert p.qty == D(1) and p.opened_at.year == 2026
