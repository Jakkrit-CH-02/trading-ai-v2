"""Order manager: turns an approved ``RiskDecision`` into exchange orders and keeps every
open position protected (SPEC 3.4).

Invariants this module exists to guarantee:
1. Nothing is sent unless the Risk Engine approved it (``submit`` is the only entry point).
2. A position never exists without an exchange-side stop. Right after a fill the stop is
   placed; if that is not done within ``stop_deadline_s`` (3 s), the position is closed.
3. Retries cannot double-trade: client order ids are deterministic and the intent is stored
   before it is sent.
4. We never chase: an unfilled entry is cancelled after ``entry_timeout_s``.
5. Exits are never loosened: stops only move up.

One open position per symbol is enforced here so stop bookkeeping stays unambiguous.
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog

from app.core.models import Side
from app.exchange.errors import (
    ExchangeError,
    IPBanned,
    OrderRejected,
    RateLimited,
    UnknownOrder,
)
from app.exchange.orders import Fill, OrderInfo, OrderStatus, OrderType
from app.exchange.trading import TradingAdapter
from app.execution.store import ExecutionStore
from app.execution.types import (
    ExecStatus,
    ExecutionResult,
    KillReport,
    Position,
    make_client_order_id,
)
from app.risk import MarketState, PortfolioState, RiskEngine, TradeIntent, decision_payload
from app.risk.engine import round_price
from app.risk.sizing import quantize_down
from app.risk.types import SymbolFilters

log = structlog.get_logger()
ZERO = Decimal(0)


@dataclass(frozen=True, slots=True)
class ExecConfig:
    quote: str = "USDT"
    entry_timeout_s: float = 30.0  # unfilled entries are cancelled, never chased
    poll_interval_s: float = 1.0
    stop_deadline_s: float = 3.0  # SPEC 3.4: no stop within 3 s => close the position
    stop_limit_buffer: Decimal = Decimal("0.002")  # stop-limit price sits 0.2% under the trigger
    tp1_close_fraction: Decimal = Decimal("0.5")
    attempts: int = 3
    cooldown_hours: int = 4  # no re-entry after a losing stop (SPEC 2.4)
    fee_rate: Decimal = Decimal("0.001")  # for the breakeven-plus-fees stop


class OrderManager:
    def __init__(
        self,
        adapter: TradingAdapter,
        risk: RiskEngine,
        store: ExecutionStore,
        config: ExecConfig | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self.adapter, self.risk, self.store = adapter, risk, store
        self.cfg = config or ExecConfig()
        self._now, self._sleep, self._mono = now, sleep, monotonic
        self.cooldowns: dict[str, datetime] = {}
        self._filters: dict[str, SymbolFilters] = {}

    # ---- plumbing -------------------------------------------------------------------------

    def _note_error(self, e: Exception) -> None:
        """Feed API health into the circuit breakers (429 / 418 / generic errors)."""
        now = self._now()
        if isinstance(e, IPBanned):
            self.risk.breakers.record_api_error(now, 418, e.retry_after)
        elif isinstance(e, RateLimited):
            self.risk.breakers.record_api_error(now, 429, e.retry_after)
        elif isinstance(e, ExchangeError) and not isinstance(e, OrderRejected | UnknownOrder):
            self.risk.breakers.record_api_error(now)

    async def _filters_for(self, symbol: str) -> SymbolFilters:
        if symbol not in self._filters:
            self._filters[symbol] = await self.adapter.symbol_filters(symbol)
        return self._filters[symbol]

    def _base(self, symbol: str) -> str:
        return symbol.removesuffix(self.cfg.quote)

    async def _event(
        self, type: str, severity: str, payload: dict[str, Any], bot_id: str | None = None
    ) -> None:
        log.log(40 if severity == "critical" else 20, f"risk_event.{type}", **payload)
        await self.store.risk_event(type, severity, payload, bot_id)

    async def _place(
        self,
        pos_or_ids: tuple[str | None, str | None],
        symbol: str,
        side: Side,
        type: OrderType,
        qty: Decimal,
        cid: str,
        leg: str,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> OrderInfo:
        """Send an order exactly once even if the network lies to us.

        On an ambiguous failure (timeout, 5xx) we ask the exchange whether the order landed
        before ever re-sending, and we re-send only with the *same* client order id."""
        bot_id, signal_id = pos_or_ids
        last: Exception | None = None
        for _ in range(self.cfg.attempts):
            try:
                info = await self.adapter.place_order(
                    symbol, side, type, qty, cid, price, stop_price
                )
            except OrderRejected as e:
                if e.code == -2010 and "Duplicate" in str(e):  # it already landed
                    info = await self.adapter.get_order(symbol, cid)
                else:
                    raise
            except (RateLimited, IPBanned) as e:
                self._note_error(e)
                raise
            except ExchangeError as e:
                self._note_error(e)
                last = e
                try:
                    info = await self.adapter.get_order(symbol, cid)  # did it land anyway?
                except UnknownOrder:
                    continue  # no: safe to retry with the same id
                except ExchangeError as e2:
                    self._note_error(e2)
                    continue
            await self.store.record_order(info, leg, bot_id, signal_id)
            return info
        raise last or ExchangeError("order placement failed")

    # ---- entry ----------------------------------------------------------------------------

    async def submit(
        self, intent: TradeIntent, portfolio: PortfolioState, market: MarketState
    ) -> ExecutionResult:
        """The only way to open a position. Risk first, then entry, then stop."""
        if await self.store.get_position(intent.symbol) is not None:
            return ExecutionResult(
                ExecStatus.REJECTED, detail="a position is already open for this symbol"
            )
        signal_id = intent.signal_id or uuid.uuid4().hex[:12]
        ids = (intent.bot_id, signal_id)
        entry_cid = make_client_order_id(intent.bot_id, signal_id, "e")
        if await self.store.has_order(entry_cid):
            return ExecutionResult(
                ExecStatus.DUPLICATE, detail="order already handled", client_order_id=entry_cid
            )

        filters = await self._filters_for(intent.symbol)
        mkt = replace(market, cooldowns={**market.cooldowns, **self.cooldowns})
        decision = self.risk.evaluate(intent, portfolio, mkt, filters)
        if not decision.approved:
            await self._event(
                "ORDER_REJECTED", "info", decision_payload(intent, decision), intent.bot_id
            )
            return ExecutionResult(
                ExecStatus.REJECTED, decision, detail=",".join(r.value for r in decision.reasons)
            )

        otype = OrderType.MARKET if intent.order_type == "MARKET" else OrderType.LIMIT
        price = decision.entry if otype == OrderType.LIMIT else None
        # persist the intent *before* sending: a crash/retry then sees it and cannot double-trade
        await self.store.record_order(
            OrderInfo(
                entry_cid,
                intent.symbol,
                Side.BUY,
                otype,
                OrderStatus.NEW,
                decision.qty,
                price=price,
            ),
            "ENTRY",
            intent.bot_id,
            signal_id,
        )
        try:
            info = await self._place(
                ids, intent.symbol, Side.BUY, otype, decision.qty, entry_cid, "ENTRY", price=price
            )
        except ExchangeError as e:
            await self._event(
                "ENTRY_FAILED",
                "warning",
                {"symbol": intent.symbol, "error": repr(e)},
                intent.bot_id,
            )
            return ExecutionResult(
                ExecStatus.NOT_FILLED,
                decision,
                detail=f"entry failed: {e}",
                client_order_id=entry_cid,
            )

        info = await self._await_fill(intent.symbol, info, ids)
        if info.executed_qty <= 0:
            return ExecutionResult(
                ExecStatus.NOT_FILLED,
                decision,
                detail="entry not filled",
                client_order_id=entry_cid,
            )

        fills = await self.adapter.fills(intent.symbol, entry_cid)
        await self.store.record_fills(fills)
        fill_seen = self._mono()  # the 3-second stop clock starts when we learn about the fill
        pos = self._position_from_fill(
            intent, decision.stop, decision.tp1, info, fills, filters, entry_cid, signal_id
        )
        pos.order_cids.append(entry_cid)
        minimum = max(filters.min_qty, filters.min_notional / pos.avg_entry)
        if pos.qty < minimum:  # too small to protect or sell: leave as dust, do not pretend
            pos.closed, pos.exit_reason = True, "dust"
            await self.store.save_position(pos)
            await self._event(
                "DUST_FILL", "warning", {"symbol": pos.symbol, "qty": str(pos.qty)}, intent.bot_id
            )
            return ExecutionResult(
                ExecStatus.NOT_FILLED, decision, pos, "fill below exchange minimum", entry_cid
            )
        await self.store.save_position(pos)  # before stops: a crash leaves a record to protect

        if await self._protect(pos, fill_seen):
            return ExecutionResult(ExecStatus.PROTECTED, decision, pos, "stop in place", entry_cid)
        return await self._emergency_close(pos, decision, "stop could not be placed in time")

    async def _await_fill(
        self, symbol: str, info: OrderInfo, ids: tuple[str | None, str | None]
    ) -> OrderInfo:
        deadline = self._mono() + self.cfg.entry_timeout_s
        while info.status.is_open and self._mono() < deadline:
            await self._sleep(self.cfg.poll_interval_s)
            try:
                info = await self.adapter.get_order(symbol, info.client_order_id)
            except ExchangeError as e:
                self._note_error(e)
        if info.status.is_open:  # do not chase: cancel what is left
            try:
                await self.adapter.cancel_order(symbol, info.client_order_id)
            except (OrderRejected, UnknownOrder):
                pass  # it filled or was cancelled in the meantime
            except ExchangeError as e:
                self._note_error(e)
            info = await self.adapter.get_order(symbol, info.client_order_id)
        await self.store.record_order(info, "ENTRY", *ids)
        return info

    def _position_from_fill(
        self,
        intent: TradeIntent,
        stop: Decimal,
        tp1: Decimal | None,
        info: OrderInfo,
        fills: list[Fill],
        filters: SymbolFilters,
        entry_cid: str,
        signal_id: str,
    ) -> Position:
        base, quote = self._base(intent.symbol), self.cfg.quote
        avg = info.avg_price or (sum((f.price * f.qty for f in fills), ZERO) / info.executed_qty)
        base_fee = sum((f.fee for f in fills if f.fee_asset == base), ZERO)
        quote_fee = sum((f.fee for f in fills if f.fee_asset == quote), ZERO)
        # Binance takes the fee from the coins you bought, so only the net quantity can be sold
        qty = quantize_down(info.executed_qty - base_fee, filters.step_size)
        return Position(
            symbol=intent.symbol,
            bot_id=intent.bot_id,
            signal_id=signal_id,
            strategy=intent.strategy,
            qty0=qty,
            qty=qty,
            avg_entry=avg,
            stop=stop,
            tp1=tp1 if intent.place_tp else None,
            tp1_close_fraction=intent.tp1_close_fraction or self.cfg.tp1_close_fraction,
            entry_cid=entry_cid,
            opened_at=self._now(),
            entry_cost=info.executed_qty * avg + quote_fee,
            base_asset=base,
            initial_stop=stop,
        )

    # ---- protection -----------------------------------------------------------------------

    async def _protect(self, pos: Position, started: float) -> bool:
        """Place exchange-side exits within the deadline. Partial protection is torn down."""
        for _ in range(self.cfg.attempts):
            remaining = self.cfg.stop_deadline_s - (self._mono() - started)
            if remaining <= 0:
                break
            try:
                await asyncio.wait_for(self._place_exits(pos), timeout=remaining)
            except (TimeoutError, ExchangeError) as e:
                if isinstance(e, ExchangeError):
                    self._note_error(e)
                log.error("stop.placement_failed", symbol=pos.symbol, error=repr(e))
                await self._cancel_everything(pos.symbol)
                continue
            pos.protected = True
            await self.store.save_position(pos)
            return True
        pos.protected = False
        return False

    async def _place_exits(self, pos: Position) -> None:
        f = await self._filters_for(pos.symbol)
        ids = (pos.bot_id, pos.signal_id)
        ver, pos.version = pos.version, pos.version + 1
        qty = pos.qty
        stop_limit = round_price(pos.stop * (1 - self.cfg.stop_limit_buffer), f.tick_size)
        tp_qty = ZERO
        if pos.tp1 is not None and not pos.tp1_done:
            tp_qty = quantize_down(qty * pos.tp1_close_fraction, f.step_size)
        rest = qty - tp_qty
        use_oco = pos.tp1 is not None and tp_qty >= f.min_qty and tp_qty * pos.tp1 >= f.min_notional
        if use_oco and not (rest >= f.min_qty and rest * stop_limit >= f.min_notional):
            tp_qty, rest = (
                qty,
                ZERO,
            )  # remainder would be unsellable dust: let the TP cover all of it
        pos.stop_cids, pos.tp_cid = [], None
        if use_oco:
            assert pos.tp1 is not None
            legs = await self.adapter.place_oco_sell(
                pos.symbol,
                tp_qty,
                pos.tp1,
                pos.stop,
                stop_limit,
                make_client_order_id(pos.bot_id, pos.signal_id, f"o{ver}"),
            )
            for leg in legs:
                await self.store.record_order(
                    leg, "TP" if leg.type == OrderType.LIMIT_MAKER else "SL", *ids
                )
                pos.order_cids.append(leg.client_order_id)
                if leg.type == OrderType.LIMIT_MAKER:
                    pos.tp_cid = leg.client_order_id
                else:
                    pos.stop_cids.append(leg.client_order_id)
        if rest > 0 or not use_oco:
            sl_qty = rest if use_oco else qty
            cid = make_client_order_id(pos.bot_id, pos.signal_id, f"r{ver}")
            info = await self._place(
                ids,
                pos.symbol,
                Side.SELL,
                OrderType.STOP_LOSS_LIMIT,
                sl_qty,
                cid,
                "SL",
                price=stop_limit,
                stop_price=pos.stop,
            )
            pos.stop_cids.append(info.client_order_id)
            pos.order_cids.append(info.client_order_id)

    async def _cancel_everything(self, symbol: str) -> None:
        for _ in range(self.cfg.attempts):
            try:
                for o in await self.adapter.cancel_all_orders(symbol):
                    await self.store.record_order(o, "CANCEL", None, None)
                return
            except ExchangeError as e:
                self._note_error(e)

    async def _emergency_close(self, pos: Position, decision: Any, reason: str) -> ExecutionResult:
        """No stop in time: flatten at market. If even that fails the position is UNPROTECTED."""
        await self._cancel_everything(pos.symbol)  # free the coins locked by any partial exit
        for attempt in range(self.cfg.attempts):
            try:
                bal = (await self.adapter.balances()).get(pos.base_asset)
                f = await self._filters_for(pos.symbol)
                qty = quantize_down(min(pos.qty, bal.free if bal else ZERO), f.step_size)
                if qty <= 0:
                    break
                cid = make_client_order_id(pos.bot_id, pos.signal_id, f"x{attempt}")
                info = await self._place(
                    (pos.bot_id, pos.signal_id),
                    pos.symbol,
                    Side.SELL,
                    OrderType.MARKET,
                    qty,
                    cid,
                    "EXIT",
                )
                pos.order_cids.append(cid)
                if info.executed_qty > 0:
                    pos.qty -= info.executed_qty
                if pos.qty <= 0:
                    await self._event(
                        "STOP_PLACEMENT_FAILED",
                        "critical",
                        {"symbol": pos.symbol, "action": "closed at market", "reason": reason},
                        pos.bot_id,
                    )
                    await self._finalize(pos, "emergency_close")
                    return ExecutionResult(ExecStatus.EMERGENCY_CLOSED, decision, pos, reason)
            except ExchangeError as e:
                self._note_error(e)
        self.risk.breakers.flag_exchange_event(f"UNPROTECTED POSITION {pos.symbol}")
        await self._event(
            "UNPROTECTED_POSITION",
            "critical",
            {"symbol": pos.symbol, "qty": str(pos.qty), "reason": reason},
            pos.bot_id,
        )
        await self.store.save_position(pos)
        return ExecutionResult(
            ExecStatus.UNPROTECTED,
            decision,
            pos,
            "position open WITHOUT a stop and could not be closed",
        )

    # ---- ongoing management ------------------------------------------------------------------

    async def sync_position(self, symbol: str) -> list[str]:
        """Observe exits, move to breakeven after TP1, and handle a stop that gapped through."""
        pos = await self.store.get_position(symbol)
        if pos is None:
            return []
        events: list[str] = []
        orders: dict[str, OrderInfo] = {}
        for cid in ([pos.tp_cid] if pos.tp_cid else []) + pos.stop_cids:
            try:
                orders[cid] = await self.adapter.get_order(symbol, cid)
            except ExchangeError as e:
                self._note_error(e)
        for o in orders.values():
            await self.store.record_order(o, "EXIT", pos.bot_id, pos.signal_id)

        tp = orders.get(pos.tp_cid) if pos.tp_cid else None
        # open quantity = bought - everything sold by any exit order (from the fills themselves)
        exit_fills: list[Fill] = []
        for cid in dict.fromkeys(pos.order_cids):
            if cid != pos.entry_cid:
                exit_fills += await self.adapter.fills(symbol, cid)
        await self.store.record_fills(exit_fills)
        pos.qty = pos.qty0 - sum((f.qty for f in exit_fills), ZERO)
        stop_filled = any(
            o.status == OrderStatus.FILLED and o.client_order_id in pos.stop_cids
            for o in orders.values()
        )
        if stop_filled or pos.qty <= 0:
            reason = (
                "stop"
                if stop_filled
                else ("tp1" if tp and tp.status == OrderStatus.FILLED else "exit")
            )
            await self._finalize(pos, reason)
            return [f"CLOSED_{reason.upper()}"]
        if tp is not None and tp.status == OrderStatus.FILLED and not pos.tp1_done:
            pos.tp1_done = True
            events.append("TP1_FILLED")
            f = await self._filters_for(symbol)
            be = round_price(pos.avg_entry * (1 + 2 * self.cfg.fee_rate), f.tick_size)
            pos.stop = max(pos.stop, be)  # breakeven + fees; never lower
            if not await self._reprotect(pos):
                return [*events, "EMERGENCY_CLOSE"]
            events.append("STOP_MOVED_TO_BREAKEVEN")
        # a triggered STOP_LOSS_LIMIT whose limit price the market already fell through never
        # fills: the stop is "in place" but useless. Get out at market.
        last = await self.adapter.last_price(symbol)
        for o in orders.values():
            if (
                o.status.is_open
                and o.type == OrderType.STOP_LOSS_LIMIT
                and o.price is not None
                and last < o.price
            ):
                await self._event(
                    "STOP_GAPPED",
                    "critical",
                    {"symbol": symbol, "last": str(last), "stop_limit": str(o.price)},
                    pos.bot_id,
                )
                res = await self._emergency_close(pos, None, "price fell through the stop-limit")
                return [*events, f"EMERGENCY_{res.status}"]
        await self.store.save_position(pos)
        return events

    async def close_position(self, symbol: str, reason: str) -> bool:
        """Leave the position now, at market (time stop, false breakout...). The exchange-side
        stop/TP lock the coins, so they are cancelled first; if the sale then fails the stop is
        put back so the position is never left naked. Returns True if it was closed."""
        pos = await self.store.get_position(symbol)
        if pos is None:
            return False
        await self._cancel_everything(symbol)
        events = await self.sync_position(symbol)
        if any(e.startswith("CLOSED_") for e in events):
            return True  # a stop/target filled while we were cancelling: nothing left to sell
        if events:  # e.g. TP1 filled meanwhile and a new stop was placed: free the coins again
            await self._cancel_everything(symbol)
        pos = await self.store.get_position(symbol)
        if pos is None:
            return True
        try:
            bal = (await self.adapter.balances()).get(pos.base_asset)
            f = await self._filters_for(symbol)
            qty = quantize_down(min(pos.qty, bal.free if bal else ZERO), f.step_size)
            cid = make_client_order_id(pos.bot_id, pos.signal_id, f"c{pos.version}")
            if qty <= 0:
                raise ExchangeError("nothing to sell")
            pos.order_cids.append(cid)
            info = await self._place(
                (pos.bot_id, pos.signal_id),
                symbol,
                Side.SELL,
                OrderType.MARKET,
                qty,
                cid,
                "EXIT",
            )
            if info.executed_qty <= 0:
                raise ExchangeError("exit order did not fill")
        except ExchangeError as e:
            self._note_error(e)
            await self._event(
                "EXIT_FAILED",
                "critical",
                {"symbol": symbol, "reason": reason, "error": repr(e)},
                pos.bot_id,
            )
            await self._reprotect(pos)  # never leave it without a stop
            return False
        await self._finalize(pos, reason)
        return True

    async def _reprotect(self, pos: Position) -> bool:
        """Cancel the current exits and place new ones (balances are locked by the old orders,
        so the new stop cannot be placed first). Failure closes the position."""
        started = self._mono()
        await self._cancel_everything(pos.symbol)
        if await self._protect(pos, started):
            return True
        await self._emergency_close(pos, None, "could not re-place stop")
        return False

    async def ensure_protected(self, symbol: str) -> bool:
        """Re-place the stop for an open position (used by the reconciler after a crash or a
        cancelled order). Returns False if it had to close the position instead."""
        pos = await self.store.get_position(symbol)
        return True if pos is None else await self._reprotect(pos)

    async def mark_flat(self, symbol: str, reason: str = "reconciled_flat") -> None:
        """The exchange holds none of it any more: record the result and close our record."""
        pos = await self.store.get_position(symbol)
        if pos is not None:
            await self._finalize(pos, reason)

    async def raise_stop(self, symbol: str, new_stop: Decimal) -> bool:
        """Trailing stop update. Stops only ever move up."""
        pos = await self.store.get_position(symbol)
        if pos is None or new_stop <= pos.stop:
            return False
        f = await self._filters_for(symbol)
        new_stop = round_price(new_stop, f.tick_size)
        if new_stop <= pos.stop or new_stop >= await self.adapter.last_price(symbol):
            return False
        old = pos.stop
        pos.stop = new_stop
        if await self._reprotect(pos):
            return True
        pos.stop = old
        return False

    async def _finalize(self, pos: Position, reason: str) -> None:
        """Record the realised result, update breakers/cooldown and close the position."""
        proceeds, fees = ZERO, ZERO
        for cid in dict.fromkeys(pos.order_cids):
            if cid == pos.entry_cid:
                continue
            for f in await self.adapter.fills(pos.symbol, cid):
                proceeds += f.price * f.qty
                fees += f.fee if f.fee_asset == self.cfg.quote else f.fee * f.price
        pnl = proceeds - fees - pos.entry_cost
        risk = pos.qty0 * (pos.avg_entry - pos.initial_stop)
        pnl_r = pnl / risk if risk > 0 else ZERO
        pos.closed, pos.exit_reason, pos.qty = True, reason, ZERO
        await self.store.save_position(pos)
        await self.store.record_trade(pos, pnl, pnl_r, fees, reason)
        self.risk.breakers.record_trade_result(pnl)
        if pnl < 0 and reason in ("stop", "emergency_close"):
            self.cooldowns[pos.symbol] = self._now() + timedelta(hours=self.cfg.cooldown_hours)
        await self._event(
            "POSITION_CLOSED",
            "info",
            {"symbol": pos.symbol, "reason": reason, "pnl": str(pnl), "pnl_r": f"{pnl_r:.2f}"},
            pos.bot_id,
        )

    # ---- kill switch ---------------------------------------------------------------------------

    async def kill_all(self, reason: str) -> KillReport:
        """Latch the kill switch first (no new entries even if the rest fails), then cancel every
        open order and flatten every position."""
        self.risk.breakers.trigger_kill(self._now(), reason)
        failures: list[str] = []
        cancelled = closed = 0
        positions = await self.store.open_positions()
        symbols = {p.symbol for p in positions}
        try:
            symbols |= {o.symbol for o in await self.adapter.open_orders()}
        except ExchangeError as e:
            failures.append(f"list open orders: {e}")
        for sym in sorted(symbols):
            for _ in range(self.cfg.attempts):
                try:
                    cancelled += len(await self.adapter.cancel_all_orders(sym))
                    break
                except ExchangeError as e:
                    self._note_error(e)
                    failures.append(f"cancel {sym}: {e}")
        for pos in positions:
            try:
                bal = (await self.adapter.balances()).get(pos.base_asset)
                f = await self._filters_for(pos.symbol)
                qty = quantize_down(min(pos.qty, bal.free if bal else ZERO), f.step_size)
                if qty > 0:
                    cid = make_client_order_id(pos.bot_id, pos.signal_id, "k")
                    pos.order_cids.append(cid)
                    await self._place(
                        (pos.bot_id, pos.signal_id),
                        pos.symbol,
                        Side.SELL,
                        OrderType.MARKET,
                        qty,
                        cid,
                        "EXIT",
                    )
                await self._finalize(pos, "kill")
                closed += 1
            except ExchangeError as e:
                failures.append(f"close {pos.symbol}: {e}")
        await self._event(
            "KILL_SWITCH",
            "critical",
            {"reason": reason, "cancelled": cancelled, "closed": closed, "failures": failures},
        )
        return KillReport(cancelled, closed, tuple(failures))
