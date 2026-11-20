"""Reconciler (SPEC 3.4.6): every 60 s compare our records with Binance and, on any
difference, **believe Binance**, fix our records and write a risk event.

It also repairs the dangerous gap a crash can leave: a position that was filled but never
got its stop. Any open position whose live stop orders do not cover its quantity is
re-protected (or closed if that fails).
"""

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from decimal import Decimal

import structlog

from app.exchange.errors import ExchangeError, UnknownOrder
from app.exchange.orders import OrderStatus, OrderType
from app.exchange.trading import TradingAdapter
from app.execution.order_manager import OrderManager
from app.execution.store import ExecutionStore
from app.risk.sizing import quantize_down

log = structlog.get_logger()
ZERO = Decimal(0)
OUR_PREFIX = "st"


@dataclass(frozen=True, slots=True)
class Mismatch:
    kind: str
    symbol: str
    detail: str
    action: str
    critical: bool = False


@dataclass(slots=True)
class ReconcileReport:
    mismatches: list[Mismatch] = field(default_factory=list)
    orders_checked: int = 0
    positions_checked: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.mismatches and not self.errors


class Reconciler:
    def __init__(
        self,
        adapter: TradingAdapter,
        store: ExecutionStore,
        manager: OrderManager,
        quote: str = "USDT",
    ) -> None:
        self.adapter, self.store, self.manager, self.quote = adapter, store, manager, quote

    async def run_once(self) -> ReconcileReport:
        rep = ReconcileReport()
        for step in (self._orders, self._orphans, self._positions):
            try:
                await step(rep)
            except ExchangeError as e:
                rep.errors.append(f"{step.__name__}: {e}")
                self.manager._note_error(e)  # API trouble feeds the circuit breakers
        for m in rep.mismatches:
            await self.store.risk_event(
                "RECONCILE_MISMATCH",
                "critical" if m.critical else "warning",
                {"kind": m.kind, "symbol": m.symbol, "detail": m.detail, "action": m.action},
            )
        return rep

    async def run_forever(
        self,
        interval_s: float = 60.0,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        while True:
            try:
                rep = await self.run_once()
                if not rep.ok:
                    log.warning("reconcile.differences", n=len(rep.mismatches), errors=rep.errors)
            except Exception:  # never let the safety loop die
                log.exception("reconcile.crashed")
            await sleep(interval_s)

    # ---- 1. orders we think are open -------------------------------------------------------

    async def _orders(self, rep: ReconcileReport) -> None:
        for mine in await self.store.open_orders():
            rep.orders_checked += 1
            try:
                real = await self.adapter.get_order(mine.symbol, mine.client_order_id)
            except UnknownOrder:
                gone = replace(mine, status=OrderStatus.CANCELED)
                await self.store.record_order(gone, "RECONCILED", None, None)
                rep.mismatches.append(
                    Mismatch("ORDER_MISSING", mine.symbol, mine.client_order_id, "marked cancelled")
                )
                continue
            if real.status != mine.status or real.executed_qty != mine.executed_qty:
                await self.store.record_order(real, "RECONCILED", None, None)
                await self.store.record_fills(
                    await self.adapter.fills(real.symbol, real.client_order_id)
                )
                rep.mismatches.append(
                    Mismatch(
                        "ORDER_STATUS",
                        mine.symbol,
                        f"{mine.client_order_id}: ours {mine.status}, exchange {real.status}",
                        "adopted exchange state",
                    )
                )

    # ---- 2. open orders on the exchange that we do not know ---------------------------------

    async def _orphans(self, rep: ReconcileReport) -> None:
        for o in await self.adapter.open_orders():
            if not o.client_order_id.startswith(OUR_PREFIX):
                continue  # someone else's order (e.g. placed by hand): not ours to touch
            if not await self.store.has_order(o.client_order_id):
                await self.store.record_order(o, "ADOPTED", None, None)
                rep.mismatches.append(
                    Mismatch("ORDER_UNKNOWN", o.symbol, o.client_order_id, "recorded in DB")
                )

    # ---- 3. positions ------------------------------------------------------------------------

    async def _positions(self, rep: ReconcileReport) -> None:
        balances = await self.adapter.balances()
        for pos in await self.store.open_positions():
            rep.positions_checked += 1
            sym = pos.symbol
            # first let the manager settle any exit that already filled
            await self.manager.sync_position(sym)
            pos = await self.store.get_position(sym)  # type: ignore[assignment]
            if pos is None:
                continue
            bal = balances.get(pos.base_asset)
            held = bal.total if bal else ZERO
            f = await self.adapter.symbol_filters(sym)
            if held < f.min_qty:
                await self.manager.mark_flat(sym)
                rep.mismatches.append(
                    Mismatch("POSITION_GONE", sym, "exchange holds none of it", "closed our record")
                )
                continue
            if quantize_down(held, f.step_size) < pos.qty:
                rep.mismatches.append(
                    Mismatch(
                        "POSITION_QTY",
                        sym,
                        f"ours {pos.qty}, exchange {held}",
                        "adopted exchange quantity",
                    )
                )
                pos.qty = quantize_down(held, f.step_size)
                await self.store.save_position(pos)
            live = await self.adapter.open_orders(sym)
            stop_qty = sum(
                (o.qty - o.executed_qty for o in live if o.type == OrderType.STOP_LOSS_LIMIT),
                ZERO,
            )
            if stop_qty + f.step_size < pos.qty:
                protected = await self.manager.ensure_protected(sym)
                rep.mismatches.append(
                    Mismatch(
                        "UNPROTECTED",
                        sym,
                        f"stops cover {stop_qty} of {pos.qty}",
                        "re-placed stop" if protected else "could not protect: closed position",
                        critical=True,
                    )
                )
