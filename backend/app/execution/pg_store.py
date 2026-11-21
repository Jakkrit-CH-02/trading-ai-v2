"""PostgreSQL ``ExecutionStore`` (SPEC section 7: orders, fills, positions, trades, risk_events).

Every method runs in its own short transaction, so a crash never leaves a half-written order
and the order manager can keep using the same object from several tasks. ``record_order`` is an
upsert keyed by client order id (the exchange-side idempotency key), so replays are harmless.
"""

import uuid
from collections.abc import Sequence
from dataclasses import fields
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, get_args, get_type_hints

import structlog
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import Fill as FillRow
from app.core.models import Order, OrderLeg, PositionStatus, RiskEvent, Side
from app.core.models import Position as PositionRow
from app.core.models import Trade as TradeRow
from app.exchange.orders import Fill, OrderInfo, OrderStatus, OrderType
from app.execution.types import Position

log = structlog.get_logger()
ZERO = Decimal(0)
_HINTS = get_type_hints(Position)


def as_uuid(value: str | None) -> uuid.UUID | None:
    """Manual orders and tests use ids that are not UUIDs; those are stored as NULL."""
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


def _is(tp: Any, kind: type) -> bool:
    return tp is kind or kind in get_args(tp)


def encode_position(p: Position) -> dict[str, Any]:
    """The whole execution Position as JSON (Decimal/datetime as strings, losslessly)."""
    out: dict[str, Any] = {}
    for f in fields(p):
        v = getattr(p, f.name)
        if isinstance(v, Decimal):
            v = str(v)
        elif isinstance(v, datetime):
            v = v.isoformat()
        elif isinstance(v, list):
            v = list(v)
        out[f.name] = v
    return out


def decode_position(d: dict[str, Any]) -> Position:
    kw: dict[str, Any] = {}
    for f in fields(Position):
        if f.name not in d:
            continue
        v, tp = d[f.name], _HINTS[f.name]
        if v is not None and _is(tp, Decimal):
            v = Decimal(v)
        elif v is not None and _is(tp, datetime):
            v = datetime.fromisoformat(v)
        elif isinstance(v, list):
            v = list(v)
        kw[f.name] = v
    return Position(**kw)


def _leg(leg: str) -> OrderLeg:
    """The order manager also records bookkeeping updates (e.g. a cancel) under other labels;
    those only update an existing row, so an unknown label must never raise."""
    try:
        return OrderLeg(leg)
    except ValueError:
        return OrderLeg.EXIT


def _order_raw(o: OrderInfo) -> dict[str, Any]:
    return {
        "executed_qty": str(o.executed_qty),
        "stop_price": None if o.stop_price is None else str(o.stop_price),
        "avg_price": None if o.avg_price is None else str(o.avg_price),
        "order_list_id": o.order_list_id,
        "ts": None if o.ts is None else o.ts.isoformat(),
    }


def order_info(row: Order) -> OrderInfo:
    raw = row.raw or {}

    def dec(key: str) -> Decimal | None:
        return None if raw.get(key) is None else Decimal(raw[key])

    return OrderInfo(
        client_order_id=row.client_order_id,
        symbol=row.symbol,
        side=Side(row.side),
        type=OrderType(row.type),
        status=OrderStatus(row.status),
        qty=row.qty,
        executed_qty=dec("executed_qty") or ZERO,
        price=row.price,
        stop_price=dec("stop_price"),
        avg_price=dec("avg_price"),
        exchange_order_id=row.exchange_order_id,
        order_list_id=raw.get("order_list_id"),
        ts=None if raw.get("ts") is None else datetime.fromisoformat(raw["ts"]),
    )


class PgExecutionStore:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def has_order(self, client_order_id: str) -> bool:
        async with self._sessions() as db:
            q = select(Order.id).where(Order.client_order_id == client_order_id)
            return (await db.execute(q)).first() is not None

    async def record_order(
        self, info: OrderInfo, leg: str, bot_id: str | None, signal_id: str | None
    ) -> None:
        stmt = pg_insert(Order).values(
            bot_id=as_uuid(bot_id),
            signal_id=as_uuid(signal_id),
            client_order_id=info.client_order_id,
            exchange_order_id=info.exchange_order_id,
            symbol=info.symbol,
            side=info.side,
            type=info.type.value,
            price=info.price,
            qty=info.qty,
            status=info.status.value,
            leg=_leg(leg),
            raw=_order_raw(info),
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[Order.client_order_id],
            set_={
                "exchange_order_id": stmt.excluded.exchange_order_id,
                "price": stmt.excluded.price,
                "qty": stmt.excluded.qty,
                "status": stmt.excluded.status,
                "raw": stmt.excluded.raw,
                "updated_at": func.now(),
            },
        )
        async with self._sessions.begin() as db:
            await db.execute(stmt)

    async def record_fills(self, fills: Sequence[Fill]) -> None:
        if not fills:
            return
        cids = {f.client_order_id for f in fills}
        async with self._sessions.begin() as db:
            found = await db.execute(
                select(Order.client_order_id, Order.id).where(Order.client_order_id.in_(cids))
            )
            ids = {cid: oid for cid, oid in found.all()}
            for f in fills:
                if f.client_order_id not in ids:
                    log.warning("fill.unknown_order", cid=f.client_order_id)
                    continue
                stmt = (
                    pg_insert(FillRow)
                    .values(
                        order_id=ids[f.client_order_id],
                        trade_id=f.trade_id,
                        price=f.price,
                        qty=f.qty,
                        fee=f.fee,
                        fee_asset=f.fee_asset,
                        is_maker=f.is_maker,
                        ts=f.ts,
                    )
                    .on_conflict_do_nothing(constraint="uq_fill_trade")
                )
                await db.execute(stmt)

    async def open_orders(self) -> list[OrderInfo]:
        open_states = [s.value for s in OrderStatus if s.is_open]
        async with self._sessions() as db:
            rows = (await db.execute(select(Order).where(Order.status.in_(open_states)))).scalars()
            return [order_info(r) for r in rows]

    async def save_position(self, position: Position) -> None:
        now = datetime.now(UTC)
        values: dict[str, Any] = {
            "bot_id": as_uuid(position.bot_id),
            "symbol": position.symbol,
            "side": Side.BUY,
            "qty": position.qty,
            "avg_entry": position.avg_entry,
            "stop": position.stop,
            "status": PositionStatus.CLOSED if position.closed else PositionStatus.OPEN,
            "opened_at": position.opened_at,
            "entry_cid": position.entry_cid,
            "state": encode_position(position),
        }
        stmt = pg_insert(PositionRow).values(**values, closed_at=now if position.closed else None)
        update: dict[str, Any] = {k: stmt.excluded[k] for k in ("qty", "stop", "status", "state")}
        update["updated_at"] = func.now()
        if position.closed:
            update["closed_at"] = func.coalesce(PositionRow.closed_at, now)
        stmt = stmt.on_conflict_do_update(index_elements=[PositionRow.entry_cid], set_=update)
        async with self._sessions.begin() as db:
            await db.execute(stmt)

    async def _open(self, db: AsyncSession, symbol: str | None = None) -> list[Position]:
        q = select(PositionRow).where(PositionRow.status == PositionStatus.OPEN)
        if symbol is not None:
            q = q.where(PositionRow.symbol == symbol)
        rows = (await db.execute(q.order_by(PositionRow.opened_at))).scalars()
        return [decode_position(r.state) for r in rows if r.state]

    async def get_position(self, symbol: str) -> Position | None:
        async with self._sessions() as db:
            found = await self._open(db, symbol)
        return found[0] if found else None

    async def open_positions(self) -> list[Position]:
        async with self._sessions() as db:
            return await self._open(db)

    async def record_trade(
        self, position: Position, pnl: Decimal, pnl_r: Decimal, fees: Decimal, reason: str
    ) -> None:
        async with self._sessions.begin() as db:
            pid = (
                await db.execute(
                    select(PositionRow.id).where(PositionRow.entry_cid == position.entry_cid)
                )
            ).scalar_one_or_none()
            if pid is None:  # save_position always runs first; never lose the result anyway
                log.error("trade.no_position", cid=position.entry_cid)
                return
            held = max(0, int((datetime.now(UTC) - position.opened_at).total_seconds() // 60))
            stmt = (
                pg_insert(TradeRow)
                .values(
                    position_id=pid,
                    pnl_usdt=pnl,
                    pnl_r=pnl_r,
                    fees=fees,
                    slippage=ZERO,
                    holding_minutes=held,
                    exit_reason=reason[:32],
                )
                .on_conflict_do_nothing(index_elements=[TradeRow.position_id])
            )
            await db.execute(stmt)

    async def risk_event(
        self, type: str, severity: str, payload: dict[str, Any], bot_id: str | None = None
    ) -> None:
        async with self._sessions.begin() as db:
            db.add(
                RiskEvent(
                    bot_id=as_uuid(bot_id), type=type[:48], severity=severity, payload=payload
                )
            )
