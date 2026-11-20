"""In-memory trading exchange for tests and dry runs.

It models the behaviours that make real order handling dangerous, so the order manager can be
proven against them without touching a network:

- balances are *locked* by open orders (a second stop on the same coins is rejected)
- an OCO locks its quantity once and one filled leg cancels the other
- STOP_LOSS_LIMIT triggers at the stop price but only fills while price is still at/above the
  limit: a gap through the limit leaves the position unprotected (``triggered`` but open)
- duplicate client order ids are rejected, like Binance (-2010)
- exchange filters (tick, step, min qty, min notional) are enforced
- failure injection (``fail_next``), artificial latency (``delays``) and partial fills

Prices move only when a test calls ``set_price``; matching happens then, deterministically.
"""

import asyncio
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.models import Side
from app.exchange.errors import ExchangeError, OrderRejected, UnknownOrder
from app.exchange.orders import Balance, Fill, OrderInfo, OrderStatus, OrderType
from app.exchange.trading import TradingAdapter
from app.risk.sizing import quantize_down
from app.risk.types import SymbolFilters

ZERO = Decimal(0)


@dataclass(slots=True)
class _Order:
    cid: str
    symbol: str
    side: Side
    type: OrderType
    qty: Decimal
    price: Decimal | None
    stop_price: Decimal | None
    lock_key: str
    list_id: str | None = None
    status: OrderStatus = OrderStatus.NEW
    executed: Decimal = ZERO
    quote: Decimal = ZERO  # sum(price * qty) of fills
    triggered: bool = False  # stop reached its trigger price


class FakeTradingExchange(TradingAdapter):
    def __init__(
        self,
        prices: dict[str, Decimal],
        free: dict[str, Decimal] | None = None,
        filters: SymbolFilters | None = None,
        fee_rate: Decimal = Decimal("0.001"),
        quote: str = "USDT",
        fee_in_base: bool = False,
    ) -> None:
        self.prices = dict(prices)
        self._free: dict[str, Decimal] = defaultdict(lambda: ZERO, free or {})
        self._locked: dict[str, Decimal] = defaultdict(lambda: ZERO)
        self.filters = filters or SymbolFilters(
            Decimal("0.01"), Decimal("0.00001"), Decimal("0.00001"), Decimal(9000), Decimal(10)
        )
        self.fee_rate = fee_rate
        self.quote = quote
        self.fee_in_base = fee_in_base  # BUY fee taken from the coins received, like Binance
        self.now = datetime(2025, 6, 11, 12, 0, tzinfo=UTC)
        self.orders: dict[tuple[str, str], _Order] = {}
        self._fills: list[Fill] = []
        self._locks: dict[str, Decimal] = {}  # lock_key -> amount reserved (quote or base)
        self._n = 0
        # test controls
        self.calls: list[tuple[str, Any]] = []
        self.delays: dict[str, float] = {}
        self._failures: dict[str, list[Exception]] = defaultdict(list)
        self.partial_fill_ratio: Decimal | None = None  # next marketable/limit fill is partial
        self.market_slippage = ZERO  # fraction worse than last price for market orders

    # ---- test controls ------------------------------------------------------------------

    def fail_next(self, method: str, exc: Exception | None = None, times: int = 1) -> None:
        for _ in range(times):
            self._failures[method].append(exc or ExchangeError(f"injected failure in {method}"))

    async def _enter(self, method: str, *args: Any) -> None:
        self.calls.append((method, args))
        if (d := self.delays.get(method)) is not None:
            await asyncio.sleep(d)
        if self._failures[method]:
            raise self._failures[method].pop(0)

    def free(self, asset: str) -> Decimal:
        return self._free[asset]

    def locked(self, asset: str) -> Decimal:
        return self._locked[asset]

    def holding(self, asset: str) -> Decimal:
        return self._free[asset] + self._locked[asset]

    # ---- helpers --------------------------------------------------------------------------

    @staticmethod
    def _base(symbol: str) -> str:
        return symbol.removesuffix("USDT")

    def _validate(self, symbol: str, qty: Decimal, price: Decimal | None) -> None:
        f = self.filters
        if qty <= 0 or qty != quantize_down(qty, f.step_size):
            raise OrderRejected("LOT_SIZE: bad quantity", -1013)
        if qty < f.min_qty or qty > f.max_qty:
            raise OrderRejected("LOT_SIZE: quantity out of range", -1013)
        if price is not None:
            if price <= 0 or price != quantize_down(price, f.tick_size):
                raise OrderRejected("PRICE_FILTER: bad price", -1013)
        ref = price if price is not None else self.prices[symbol]
        if qty * ref < f.min_notional:
            raise OrderRejected("MIN_NOTIONAL", -1013)

    def _info(self, o: _Order) -> OrderInfo:
        return OrderInfo(
            client_order_id=o.cid,
            symbol=o.symbol,
            side=o.side,
            type=o.type,
            status=o.status,
            qty=o.qty,
            executed_qty=o.executed,
            price=o.price,
            stop_price=o.stop_price,
            avg_price=(o.quote / o.executed) if o.executed else None,
            exchange_order_id=str(abs(hash(o.cid)) % 10**9),
            order_list_id=o.list_id,
            ts=self.now,
        )

    def _lock(self, key: str, asset: str, amount: Decimal) -> None:
        if self._free[asset] < amount:
            raise OrderRejected("Account has insufficient balance for requested action.", -2010)
        self._free[asset] -= amount
        self._locked[asset] += amount
        self._locks[key] = amount

    def _release(self, key: str, asset: str) -> None:
        amount = self._locks.pop(key, ZERO)
        self._locked[asset] -= amount
        self._free[asset] += amount

    def _siblings_open(self, o: _Order) -> bool:
        return any(
            x.lock_key == o.lock_key and x.status.is_open
            for x in self.orders.values()
            if x is not o
        )

    def _close_order(self, o: _Order, status: OrderStatus) -> None:
        o.status = status
        if not self._siblings_open(o):
            asset = self.quote if o.side == Side.BUY else self._base(o.symbol)
            self._release(o.lock_key, asset)

    def _execute(self, o: _Order, qty: Decimal, price: Decimal, maker: bool) -> None:
        base, fee = self._base(o.symbol), qty * price * self.fee_rate
        fee_asset = self.quote
        if o.side == Side.BUY:
            reserved = self._locks[o.lock_key]
            if self.fee_in_base:
                fee_asset, fee = base, qty * self.fee_rate
                used = min(reserved, qty * price)
                self._free[base] += qty - fee
            else:
                used = min(reserved, qty * price + fee)
                self._free[base] += qty
            self._locks[o.lock_key] = reserved - used
            self._locked[self.quote] -= used
        else:
            self._locks[o.lock_key] -= qty
            self._locked[base] -= qty
            self._free[self.quote] += qty * price - fee
        o.executed += qty
        o.quote += qty * price
        self._fills.append(
            Fill(
                o.cid,
                o.symbol,
                f"t{len(self._fills) + 1}",
                price,
                qty,
                fee,
                fee_asset,
                maker,
                self.now,
            )
        )
        if o.executed >= o.qty:
            o.status = OrderStatus.FILLED
            if o.list_id is not None:  # OCO: the sibling leg is cancelled
                for x in self.orders.values():
                    if x.list_id == o.list_id and x is not o and x.status.is_open:
                        x.status = OrderStatus.CANCELED
            if not self._siblings_open(o):
                asset = self.quote if o.side == Side.BUY else base
                self._release(o.lock_key, asset)
        else:
            o.status = OrderStatus.PARTIALLY_FILLED

    def _fill_qty(self, o: _Order) -> Decimal:
        remaining = o.qty - o.executed
        if self.partial_fill_ratio is not None:
            part = quantize_down(remaining * self.partial_fill_ratio, self.filters.step_size)
            self.partial_fill_ratio = None
            return min(max(part, self.filters.min_qty), remaining)
        return remaining

    def _match(self, o: _Order) -> None:
        if not o.status.is_open:
            return
        px = self.prices[o.symbol]
        if o.type in (OrderType.LIMIT, OrderType.LIMIT_MAKER) and o.price is not None:
            crosses = px <= o.price if o.side == Side.BUY else px >= o.price
            if crosses:
                self._execute(o, self._fill_qty(o), o.price, maker=True)
        elif (
            o.type == OrderType.STOP_LOSS_LIMIT and o.stop_price is not None and o.price is not None
        ):
            if px <= o.stop_price:
                o.triggered = True
            if o.triggered and px >= o.price:  # a gap below the limit leaves it unfilled
                self._execute(o, o.qty - o.executed, o.price, maker=False)

    # ---- TradingAdapter ---------------------------------------------------------------------

    async def symbol_filters(self, symbol: str) -> SymbolFilters:
        await self._enter("symbol_filters", symbol)
        return self.filters

    async def balances(self) -> dict[str, Balance]:
        await self._enter("balances")
        assets = set(self._free) | set(self._locked)
        return {a: Balance(a, self._free[a], self._locked[a]) for a in assets}

    async def last_price(self, symbol: str) -> Decimal:
        await self._enter("last_price", symbol)
        return self.prices[symbol]

    async def place_order(
        self,
        symbol: str,
        side: Side,
        type: OrderType,
        qty: Decimal,
        client_order_id: str,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> OrderInfo:
        await self._enter("place_order", symbol, side, type, qty, client_order_id, price)
        if (symbol, client_order_id) in self.orders:
            raise OrderRejected("Duplicate order sent.", -2010)
        self._validate(symbol, qty, price if type != OrderType.MARKET else None)
        px = self.prices[symbol]
        if type == OrderType.LIMIT_MAKER and price is not None:
            if (side == Side.BUY and price >= px) or (side == Side.SELL and price <= px):
                raise OrderRejected("Order would immediately match and take.", -2010)
        o = _Order(
            client_order_id, symbol, side, type, qty, price, stop_price, lock_key=client_order_id
        )
        if side == Side.BUY:
            ref = (price if price is not None else px * (1 + self.market_slippage)) * (
                1 + self.fee_rate
            )
            self._lock(o.lock_key, self.quote, qty * ref)
        else:
            self._lock(o.lock_key, self._base(symbol), qty)
        self.orders[(symbol, client_order_id)] = o
        if type == OrderType.MARKET:
            fill_px = (
                px * (1 + self.market_slippage)
                if side == Side.BUY
                else px * (1 - self.market_slippage)
            )
            self._execute(o, self._fill_qty(o), fill_px, maker=False)
            if o.status.is_open:  # partial market fill: the rest is cancelled (IOC semantics)
                self._close_order(o, OrderStatus.CANCELED)
        elif type == OrderType.LIMIT and price is not None:
            marketable = price >= px if side == Side.BUY else price <= px
            if marketable:
                self._execute(o, self._fill_qty(o), px, maker=False)
        else:
            self._match(o)
        return self._info(o)

    async def place_oco_sell(
        self,
        symbol: str,
        qty: Decimal,
        tp_price: Decimal,
        stop_price: Decimal,
        stop_limit_price: Decimal,
        client_order_id: str,
    ) -> list[OrderInfo]:
        await self._enter("place_oco_sell", symbol, qty, tp_price, stop_price, client_order_id)
        tp_id, sl_id = f"{client_order_id}-tp", f"{client_order_id}-sl"
        if (symbol, tp_id) in self.orders or (symbol, sl_id) in self.orders:
            raise OrderRejected("Duplicate order sent.", -2010)
        self._validate(symbol, qty, tp_price)
        self._validate(symbol, qty, stop_limit_price)
        px = self.prices[symbol]
        if not (stop_price < px < tp_price):
            raise OrderRejected("OCO price relationship violated for a sell.", -1013)
        self._lock(client_order_id, self._base(symbol), qty)
        tp = _Order(
            tp_id,
            symbol,
            Side.SELL,
            OrderType.LIMIT_MAKER,
            qty,
            tp_price,
            None,
            client_order_id,
            client_order_id,
        )
        sl = _Order(
            sl_id,
            symbol,
            Side.SELL,
            OrderType.STOP_LOSS_LIMIT,
            qty,
            stop_limit_price,
            stop_price,
            client_order_id,
            client_order_id,
        )
        self.orders[(symbol, tp_id)], self.orders[(symbol, sl_id)] = tp, sl
        return [self._info(tp), self._info(sl)]

    async def cancel_order(self, symbol: str, client_order_id: str) -> OrderInfo:
        await self._enter("cancel_order", symbol, client_order_id)
        o = self.orders.get((symbol, client_order_id))
        if o is None:
            raise UnknownOrder(client_order_id)
        if not o.status.is_open:
            raise OrderRejected("Unknown order sent.", -2011)
        self._close_order(o, OrderStatus.CANCELED)
        return self._info(o)

    async def cancel_all_orders(self, symbol: str) -> list[OrderInfo]:
        await self._enter("cancel_all_orders", symbol)
        out = []
        for o in self.orders.values():
            if o.symbol == symbol and o.status.is_open:
                self._close_order(o, OrderStatus.CANCELED)
                out.append(self._info(o))
        return out

    async def get_order(self, symbol: str, client_order_id: str) -> OrderInfo:
        await self._enter("get_order", symbol, client_order_id)
        o = self.orders.get((symbol, client_order_id))
        if o is None:
            raise UnknownOrder(client_order_id)
        return self._info(o)

    async def open_orders(self, symbol: str | None = None) -> list[OrderInfo]:
        await self._enter("open_orders", symbol)
        return [
            self._info(o)
            for o in self.orders.values()
            if o.status.is_open and (symbol is None or o.symbol == symbol)
        ]

    async def fills(self, symbol: str, client_order_id: str) -> list[Fill]:
        await self._enter("fills", symbol, client_order_id)
        return [
            f for f in self._fills if f.symbol == symbol and f.client_order_id == client_order_id
        ]

    # ---- market movement (test driver) ----------------------------------------------------

    def set_price(self, symbol: str, price: Decimal) -> None:
        """Move the market and run matching for every open order on the symbol."""
        self.prices[symbol] = price
        for o in list(self.orders.values()):
            if o.symbol == symbol:
                self._match(o)
