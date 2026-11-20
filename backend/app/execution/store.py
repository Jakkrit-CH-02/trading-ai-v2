"""Persistence boundary for execution state. The order manager only talks to this protocol,
so it is testable in memory; ``PgExecutionStore`` (below) writes the SPEC section 7 tables."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Any, Protocol

from app.exchange.orders import Fill, OrderInfo
from app.execution.types import Position


class ExecutionStore(Protocol):
    async def has_order(self, client_order_id: str) -> bool: ...

    async def record_order(
        self, info: OrderInfo, leg: str, bot_id: str | None, signal_id: str | None
    ) -> None:
        """Insert or update (by client order id)."""

    async def record_fills(self, fills: Sequence[Fill]) -> None: ...

    async def open_orders(self) -> list[OrderInfo]:
        """Orders this system believes are still open (for reconciliation)."""

    async def save_position(self, position: Position) -> None: ...

    async def get_position(self, symbol: str) -> Position | None: ...

    async def open_positions(self) -> list[Position]: ...

    async def record_trade(
        self, position: Position, pnl: Decimal, pnl_r: Decimal, fees: Decimal, reason: str
    ) -> None: ...

    async def risk_event(
        self, type: str, severity: str, payload: dict[str, Any], bot_id: str | None = None
    ) -> None: ...


class InMemoryExecutionStore:
    def __init__(self) -> None:
        self.orders: dict[str, tuple[OrderInfo, str, str | None, str | None]] = {}
        self.fills: dict[tuple[str, str], Fill] = {}
        self.positions: dict[str, Position] = {}
        self.trades: list[dict[str, Any]] = []
        self.events: list[dict[str, Any]] = []

    async def has_order(self, client_order_id: str) -> bool:
        return client_order_id in self.orders

    async def record_order(
        self, info: OrderInfo, leg: str, bot_id: str | None, signal_id: str | None
    ) -> None:
        self.orders[info.client_order_id] = (info, leg, bot_id, signal_id)

    async def record_fills(self, fills: Sequence[Fill]) -> None:
        for f in fills:
            self.fills[(f.client_order_id, f.trade_id)] = f

    async def open_orders(self) -> list[OrderInfo]:
        return [o for o, *_ in self.orders.values() if o.status.is_open]

    async def save_position(self, position: Position) -> None:
        self.positions[position.symbol] = position

    async def get_position(self, symbol: str) -> Position | None:
        p = self.positions.get(symbol)
        return p if p is not None and not p.closed else None

    async def open_positions(self) -> list[Position]:
        return [p for p in self.positions.values() if not p.closed]

    async def record_trade(
        self, position: Position, pnl: Decimal, pnl_r: Decimal, fees: Decimal, reason: str
    ) -> None:
        self.trades.append(
            {"symbol": position.symbol, "pnl": pnl, "pnl_r": pnl_r, "fees": fees, "reason": reason}
        )

    async def risk_event(
        self, type: str, severity: str, payload: dict[str, Any], bot_id: str | None = None
    ) -> None:
        self.events.append(
            {"type": type, "severity": severity, "payload": payload, "bot_id": bot_id}
        )

    def event_types(self) -> list[str]:
        return [e["type"] for e in self.events]
