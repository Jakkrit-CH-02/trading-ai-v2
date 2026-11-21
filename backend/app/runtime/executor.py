"""From decisions to orders, and from orders to managed positions.

``act``   : a TAKEN signal -> Risk Engine -> OrderManager (entry, exchange-side stop/TP).
``manage``: every closed bar, apply the strategy's own exit rules (false breakout, time stop,
            trailing stop) to the open position, exactly as the backtester does.
``tick``  : once in a while - honour the kill switch, snapshot equity, keep reconcilers alive.
"""

import asyncio
import contextlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import numpy as np
import pandas as pd
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.backtest.engine import BacktestConfig
from app.core.models import Bot, BotStatus, Decision, RiskEvent, Side
from app.core.models import Signal as SignalRow
from app.exchange.errors import ExchangeError
from app.exchange.types import INTERVAL_MS
from app.execution.portfolio import build_portfolio
from app.execution.types import ExecStatus
from app.marketdata import indicators as ind
from app.marketdata.store import CandleStore
from app.notify.telegram import Notifier, NullNotifier
from app.risk.engine import round_price
from app.risk.types import MarketState, PortfolioState, TradeIntent
from app.runtime.accounts import AccountPool, AccountRuntime
from app.runtime.equity import baselines, record_snapshot
from app.runtime.frames import load_features
from app.runtime.plan import ExitPlan
from app.runtime.runner import BotSpec, Judged, build_strategy, load_bot
from app.runtime.signals_store import update_outcome

log = structlog.get_logger()
ZERO = Decimal(0)
RECONCILE_EVERY_S = 60.0


@dataclass
class Executor:
    sessions: async_sessionmaker[AsyncSession]
    pool: AccountPool
    candles: CandleStore
    symbols: list[str]
    config: BacktestConfig = field(default_factory=BacktestConfig)
    notifier: Notifier = field(default_factory=NullNotifier)
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    wait_for_htf_s: float = 90.0
    _recon: dict[uuid.UUID | None, asyncio.Task[None]] = field(default_factory=dict)
    _last_snapshot: dict[uuid.UUID | None, datetime] = field(default_factory=dict)

    # ---- state shared by act / tick -----------------------------------------------------------

    async def _portfolio(self, rt: AccountRuntime, now: datetime) -> PortfolioState:
        balances = await rt.adapter.balances()
        prices: dict[str, Decimal] = {}
        for sym in self.symbols:
            held = balances.get(sym.removesuffix("USDT"))
            if held is not None and held.total > 0:
                prices[sym] = await rt.adapter.last_price(sym)
        day, week, peak = await baselines(self.sessions, rt.account_id, now)
        return await build_portfolio(
            balances, prices, rt.store, day_start=day, week_start=week, peak=peak
        )

    async def _event(
        self, bot_id: uuid.UUID | None, type: str, severity: str, **payload: Any
    ) -> None:
        async with self.sessions.begin() as db:
            db.add(RiskEvent(bot_id=bot_id, type=type, severity=severity, payload=payload))

    # ---- entries --------------------------------------------------------------------------------

    async def act(self, j: Judged) -> None:
        """Open the position for a new TAKEN signal. Never raises: a failure is recorded."""
        bot, sig = j.bot, j.decision.signal
        try:
            await self._enter(j)
        except Exception as e:  # nothing here may kill the stream loop
            log.exception("executor.act_failed", bot=bot.name, symbol=sig.symbol)
            await update_outcome(self.sessions, j.signal_id, f"ERROR: {e!r}", Decision.REJECTED)
            await self._event(bot.id, "ORDER_ERROR", "critical", symbol=sig.symbol, error=repr(e))

    async def _enter(self, j: Judged) -> None:
        bot, sig, sc = j.bot, j.decision.signal, j.decision.score
        rt = await self.pool.get(bot.account_id, await self._risk_row(bot))
        if rt is None:
            await update_outcome(
                self.sessions, j.signal_id, "no usable exchange account", Decision.REJECTED
            )
            await self._event(
                bot.id, "ACCOUNT_UNAVAILABLE", "critical", account=str(bot.account_id)
            )
            return
        if await rt.store.get_position(sig.symbol) is not None:
            await update_outcome(
                self.sessions, j.signal_id, "position already open", Decision.SKIPPED
            )
            return
        now = self.now()
        pf = await self._portfolio(rt, now)
        rt.breakers.record_tick(now)  # the price below is fetched right now
        rt.breakers.observe_equity(now, pf)
        last = await rt.adapter.last_price(sig.symbol)
        f = await rt.adapter.symbol_filters(sig.symbol)
        # a marketable limit: fills like the backtest's taker order, but never worse than the
        # slippage the backtest assumed (SPEC 3.4: no market orders, no chasing)
        entry = round_price(last * (1 + rt.profile.slippage_rate), f.tick_size)
        intent = TradeIntent(
            symbol=sig.symbol,
            side=Side.BUY,
            entry=entry,
            stop=sig.stop,
            strategy=sig.strategy,
            tp1=sig.tp1 if sig.tp1 is not None else sig.rr_target,
            order_type="LIMIT",
            size_factor=sc.size_factor,
            signal_id=str(j.signal_id),
            bot_id=str(bot.id),
            place_tp=sig.tp1 is not None,
            tp1_close_fraction=sig.tp1_close_fraction,
        )
        market = MarketState(now=now, bot_status=bot.status, data_age_s=0.0, clock_drift_ms=0.0)
        res = await rt.manager.submit(intent, pf, market)
        log.info("executor.submitted", bot=bot.name, symbol=sig.symbol, status=res.status.value)
        if res.status == ExecStatus.REJECTED:
            await update_outcome(self.sessions, j.signal_id, res.detail, Decision.REJECTED)
        elif res.status != ExecStatus.PROTECTED:
            await update_outcome(self.sessions, j.signal_id, f"{res.status.value}: {res.detail}")
        if res.status == ExecStatus.UNPROTECTED:
            await self.notifier.send(f"CRITICAL: {sig.symbol} is open WITHOUT a stop")

    async def _risk_row(self, bot: BotSpec) -> Any:
        from app.core.models import RiskProfile as RiskProfileRow

        async with self.sessions() as db:
            row = await db.get(Bot, bot.id)
            return await db.get(RiskProfileRow, row.risk_profile_id) if row else None

    # ---- exits ----------------------------------------------------------------------------------

    async def manage(self, symbol: str, interval: str, bar_open: datetime) -> None:
        """Apply the strategy's exit rules to this symbol's position at the close of a bar."""
        for rt in self.pool.runtimes():
            pos = await rt.store.get_position(symbol)
            if pos is None or pos.bot_id is None:
                continue
            try:
                async with rt.lock:
                    await self._manage_one(rt, pos.bot_id, symbol, interval, bar_open)
            except Exception:
                log.exception("executor.manage_failed", symbol=symbol)
                await self._event(uuid.UUID(pos.bot_id), "MANAGE_ERROR", "critical", symbol=symbol)

    async def _manage_one(
        self, rt: AccountRuntime, bot_id: str, symbol: str, interval: str, bar_open: datetime
    ) -> None:
        bot = await load_bot(self.sessions, uuid.UUID(bot_id))
        if bot is None:
            return
        strat = build_strategy(bot.strategy, bot.params)
        if strat.exec_interval != interval:
            return
        await rt.manager.sync_position(symbol)  # fills, TP1 -> breakeven, gapped stop
        pos = await rt.store.get_position(symbol)
        if pos is None:
            return
        async with self.sessions() as db:
            sig_row = await db.get(SignalRow, uuid.UUID(pos.signal_id)) if pos.signal_id else None
        plan = ExitPlan.from_json(sig_row.exit_plan if sig_row else None)
        feats = await load_features(
            self.candles, strat, symbol, bar_open, wait_s=self.wait_for_htf_s
        )
        n, ms = len(feats), INTERVAL_MS[strat.exec_interval]
        entry_bar = pos.opened_at.astimezone(UTC).timestamp() // (ms / 1000) * (ms / 1000)
        first = int(feats.index.searchsorted(pd.Timestamp(entry_bar, unit="s", tz="UTC")))
        held = n - first  # the entry bar counts as bar 1 (as in the backtester)
        close = Decimal(repr(float(feats["close"][-1])))
        if plan.false_breakout is not None and held <= plan.false_breakout[1]:
            if close < plan.false_breakout[0]:
                await rt.manager.close_position(symbol, "false_breakout")
                return
        if plan.time_stop_bars is not None and held >= plan.time_stop_bars:
            await rt.manager.close_position(symbol, "time_stop")
            return
        t = plan.trail
        if t is not None and (not t.after_tp1 or pos.tp1_done):
            highest = max(pos.avg_entry, Decimal(repr(float(np.max(feats["high"][first:])))))
            atr = ind.atr(
                pd.Series(feats["high"]),
                pd.Series(feats["low"]),
                pd.Series(feats["close"]),
                t.period,
            ).to_numpy()[-1]
            if not np.isnan(atr):
                level = highest - Decimal(repr(float(atr))) * Decimal(repr(t.mult))
                if level > pos.stop:  # ratchets up only; exchange stop is replaced
                    if level >= await rt.adapter.last_price(symbol):
                        # the new stop would sit above the market: the backtest stops out on the
                        # next bar, and an exchange cannot hold such a stop, so leave now
                        await rt.manager.close_position(symbol, "trail")
                    else:
                        await rt.manager.raise_stop(symbol, level)

    # ---- housekeeping ---------------------------------------------------------------------------

    async def _check_kill(self, rt: AccountRuntime, now: datetime) -> None:
        """A tripped kill switch (drawdown, or a human) flattens the account and latches bots."""
        if not rt.breakers.kill_switch_active or rt.kill_handled:
            return
        rt.kill_handled = True
        async with rt.lock:
            report = await rt.manager.kill_all("kill switch")
        async with self.sessions.begin() as db:
            await db.execute(
                update(Bot)
                .where(Bot.account_id == rt.account_id, Bot.status != BotStatus.DRAFT)
                .values(status=BotStatus.KILLED)
            )
        await self.notifier.send(
            f"KILL SWITCH: cancelled {report.cancelled_orders}, closed {report.closed_positions}"
            + (f", FAILURES: {list(report.failures)}" if report.failures else "")
        )

    async def _sync_kill_state(self, rt: AccountRuntime) -> None:
        """The database is the source of truth for the kill switch (the API sets it, and a human
        resets it with 2FA): latch when any bot of the account is KILLED, release when none is."""
        async with self.sessions() as db:
            killed = (
                await db.execute(
                    select(Bot.id).where(
                        Bot.account_id == rt.account_id, Bot.status == BotStatus.KILLED
                    )
                )
            ).first() is not None
        now = self.now()
        if killed and not rt.breakers.kill_switch_active:
            rt.breakers.trigger_kill(now, "kill switch set in the database")
        if not killed and rt.kill_handled and rt.breakers.kill_switch_active:
            rt.breakers.reset_kill(totp_verified=True)  # the API already verified the 2FA code
            rt.kill_handled = False
        if not killed and not rt.breakers.kill_switch_active:
            rt.kill_handled = False

    async def tick(self) -> None:
        """Run every few seconds."""
        async with self.sessions() as db:
            account_ids = list(
                (
                    await db.execute(
                        select(Bot.account_id).where(Bot.status != BotStatus.DRAFT).distinct()
                    )
                ).scalars()
            )
        for account_id in [None, *account_ids]:
            rt = await self.pool.get(account_id, await self._profile_row_for(account_id))
            if rt is None:
                continue
            self._ensure_reconciler(rt)
            try:
                await self._sync_kill_state(rt)
                now = self.now()
                last = self._last_snapshot.get(rt.account_id)
                if last is None or now - last >= timedelta(seconds=60):
                    pf = await self._portfolio(rt, now)
                    rt.breakers.observe_equity(now, pf)
                    await record_snapshot(self.sessions, rt.account_id, now, pf)
                    self._last_snapshot[rt.account_id] = now
                await self._check_kill(rt, now)
            except ExchangeError as e:
                log.warning("executor.tick_exchange_error", account=str(account_id), error=str(e))
            except Exception:
                log.exception("executor.tick_failed", account=str(account_id))

    async def _profile_row_for(self, account_id: uuid.UUID | None) -> Any:
        if account_id is None:
            return None
        from app.core.models import RiskProfile as RiskProfileRow

        async with self.sessions() as db:
            bot = (
                await db.execute(select(Bot).where(Bot.account_id == account_id).limit(1))
            ).scalar_one_or_none()
            return await db.get(RiskProfileRow, bot.risk_profile_id) if bot else None

    def _ensure_reconciler(self, rt: AccountRuntime) -> None:
        task = self._recon.get(rt.account_id)
        if task is None or task.done():
            self._recon[rt.account_id] = asyncio.create_task(self._reconcile_loop(rt))

    async def _reconcile_loop(self, rt: AccountRuntime) -> None:
        while True:
            try:
                async with rt.lock:
                    rep = await rt.reconciler.run_once()
                if not rep.ok:
                    log.warning("reconcile.differences", n=len(rep.mismatches), errors=rep.errors)
            except Exception:  # the safety loop must never die
                log.exception("reconcile.crashed")
            await asyncio.sleep(RECONCILE_EVERY_S)

    async def aclose(self) -> None:
        for task in self._recon.values():
            task.cancel()
        for task in self._recon.values():
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await self.pool.aclose()
