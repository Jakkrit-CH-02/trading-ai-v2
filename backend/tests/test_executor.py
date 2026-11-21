"""Executor + runner + OrderManager + PostgreSQL + a fake exchange: closed candle -> signal ->
Risk Engine -> entry -> exchange-side stop -> managed exits -> kill switch."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncEngine

from app.backtest.riskgate import RiskGate
from app.core.db import make_session_factory
from app.core.models import (
    Bot,
    BotStatus,
    Decision,
    EquitySnapshot,
    ExchangeAccount,
    Order,
    RiskEvent,
)
from app.core.models import Signal as SignalRow
from app.exchange.fake import FakeTradingExchange
from app.exchange.orders import OrderType
from app.exchange.types import INTERVAL_MS
from app.execution import ExecConfig, PgExecutionStore
from app.marketdata.store import InMemoryCandleStore
from app.runtime.accounts import AccountPool
from app.runtime.executor import Executor
from app.runtime.runner import BotRunner, Judged, build_strategy
from app.strategies.decision import decide_at_close
from tests.conftest import needs_pg
from tests.risk_helpers import FILTERS
from tests.test_runner import CFG, load_market, make_bot

pytestmark = needs_pg
D = Decimal
# a wider target (3R) so that signals clear the Risk Engine's 1.5 R:R-after-costs minimum on the
# synthetic market's tight stops
PARAMS = {"tp1_r": 3.0}


class World:
    def __init__(self, engine: AsyncEngine) -> None:
        self.sessions = make_session_factory(engine)
        self.candles = InMemoryCandleStore()
        self.ex: FakeTradingExchange | None = None
        self.t = datetime(2030, 1, 1, tzinfo=UTC)
        self.pool = AccountPool(
            self.sessions,
            PgExecutionStore(self.sessions),
            lambda _row: self.ex,
            config=ExecConfig(entry_timeout_s=5.0, poll_interval_s=0.01),
            now=lambda: self.t,
        )
        self.executor = Executor(
            self.sessions,
            self.pool,
            self.candles,
            ["BTCUSDT"],
            CFG,
            now=lambda: self.t,
            wait_for_htf_s=0.0,
        )
        self.runner = BotRunner(
            self.sessions,
            self.candles,
            CFG,
            wait_for_htf_s=0.0,
            act=self.executor.act,
            now=lambda: self.t,
        )

    def exchange(self, price: Decimal, usdt: int = 10_000) -> FakeTradingExchange:
        self.ex = FakeTradingExchange({"BTCUSDT": price}, free={"USDT": D(usdt)}, filters=FILTERS)
        return self.ex

    async def fire(self, bar: datetime, late_s: float = 10) -> list[Judged]:
        self.t = bar + timedelta(milliseconds=INTERVAL_MS["1h"]) + timedelta(seconds=late_s)
        await self.executor.manage("BTCUSDT", "1h", bar)
        return await self.runner.on_candle_closed("BTCUSDT", "1h", bar)

    async def count(self, model: type) -> int:
        async with self.sessions() as db:
            return int((await db.execute(select(func.count()).select_from(model))).scalar_one())


@pytest.fixture
async def w(pg_engine: AsyncEngine) -> AsyncIterator[World]:
    world = World(pg_engine)
    yield world
    await world.executor.aclose()


async def taken_signal(w: World) -> tuple[Any, int, uuid.UUID]:
    """A bot, the market, an exchange priced at the signal bar's close, and the bar index."""
    bot_id = await make_bot(w.sessions, params=PARAMS)
    feats, _ = await load_market(_Shim(w))  # type: ignore[arg-type]
    i = approved_bar(feats)
    w.exchange(D(repr(round(float(feats["close"][i]), 2))))
    return feats, i, bot_id


def approved_bar(feats: Any) -> int:
    """A bar whose signal is TAKEN *and* passes the Risk Engine at the live entry price (the
    synthetic market is full of signals sitting right at the 1.5 R:R limit)."""
    strat = build_strategy("s1", PARAMS)
    gate = RiskGate(D("0.005"), D("0.001"), D("0.0005"), D("0.25"), D(10), D(10_000))
    for i in range(2500, len(feats)):
        bd = decide_at_close(strat, feats, i, CFG.weights, CFG.min_quote_volume_24h, False)
        if bd is None or bd.decision != Decision.TAKEN:
            continue
        gate.on_bar_close(feats.time(i), D(10_000))  # feeds the freshness check
        fill = D(repr(round(float(feats["close"][i]) * 1.0005, 2)))
        if gate.decide(
            feats.time(i), D(10_000), "BTCUSDT", fill, bd.signal, bd.score.size_factor
        ).approved:
            return i
    raise AssertionError("no signal passes the Risk Engine in the synthetic market")


class _Shim:
    """``load_market`` only needs ``.candles``."""

    def __init__(self, w: World) -> None:
        self.candles = w.candles


async def test_a_taken_signal_becomes_a_protected_position_with_an_exchange_side_stop(
    w: World,
) -> None:
    feats, i, bot_id = await taken_signal(w)
    out = await w.fire(feats.time(i))
    assert len(out) == 1 and out[0].decision.decision == Decision.TAKEN

    pos = await w.pool.runtimes()[0].store.get_position("BTCUSDT")
    assert pos is not None and pos.protected and pos.bot_id == str(bot_id)
    assert pos.signal_id == str(out[0].signal_id)
    assert pos.stop == out[0].decision.signal.stop or pos.stop <= out[0].decision.signal.stop
    assert w.ex is not None
    assert any(
        o.type == OrderType.STOP_LOSS_LIMIT and o.status.is_open for o in w.ex.orders.values()
    )
    assert w.ex.holding("BTC") > 0
    async with w.sessions() as db:
        rows = (await db.execute(select(Order))).scalars().all()
        sig = (await db.execute(select(SignalRow))).scalar_one()
    assert rows and all(o.bot_id == bot_id for o in rows)
    assert sig.decision == Decision.TAKEN
    # risk per trade stays within the profile (0.5% of 10 000 USDT + rounding)
    risk = pos.qty0 * (pos.avg_entry - pos.initial_stop)
    assert risk <= D(10_000) * D("0.0051")


async def test_replaying_the_candle_does_not_buy_twice(w: World) -> None:
    feats, i, _ = await taken_signal(w)
    await w.fire(feats.time(i))
    again = await w.fire(feats.time(i))
    assert again[0].is_new is False
    assert w.ex is not None
    buys = [o for o in w.ex.orders.values() if o.side.value == "BUY"]
    assert len(buys) == 1


async def test_the_risk_engine_can_refuse_and_the_signal_says_why(w: World) -> None:
    feats, i, _ = await taken_signal(w)
    w.exchange(D(repr(round(float(feats["close"][i]), 2))), usdt=5)  # too little to trade
    await w.fire(feats.time(i))
    async with w.sessions() as db:
        sig = (await db.execute(select(SignalRow))).scalar_one()
    assert sig.decision == Decision.REJECTED and sig.reject_reason
    assert w.ex is not None and not w.ex.orders  # nothing reached the exchange


async def test_no_usable_account_rejects_with_an_event_instead_of_crashing(w: World) -> None:
    feats, i, bot_id = await taken_signal(w)
    w.ex = None  # the adapter factory returns nothing
    await w.fire(feats.time(i))
    async with w.sessions() as db:
        sig = (await db.execute(select(SignalRow))).scalar_one()
        ev = (await db.execute(select(RiskEvent.type, RiskEvent.bot_id))).all()
    assert sig.decision == Decision.REJECTED and "account" in (sig.reject_reason or "")
    assert ("ACCOUNT_UNAVAILABLE", bot_id) in [tuple(e) for e in ev]


async def _open_position(w: World) -> tuple[Any, int, Any]:
    feats, i, _ = await taken_signal(w)
    await w.fire(feats.time(i))
    rt = w.pool.runtimes()[0]
    pos = await rt.store.get_position("BTCUSDT")
    assert pos is not None
    return feats, i, rt


async def set_plan(w: World, plan: dict[str, Any]) -> None:
    async with w.sessions.begin() as db:
        await db.execute(update(SignalRow).values(exit_plan=plan))


async def test_time_stop_closes_at_market_after_n_bars(w: World) -> None:
    feats, i, rt = await _open_position(w)
    await set_plan(w, {"time_stop_bars": 3})
    assert w.ex is not None
    for k in (1, 2):  # bars 2 and 3 of the trade: still inside
        w.ex.prices["BTCUSDT"] = D(repr(round(float(feats["close"][i + k]), 2)))
        await w.fire(feats.time(i + k))
    pos = await rt.store.get_position("BTCUSDT")
    if pos is None:  # the synthetic path may have hit the stop first: then there is no time stop
        pytest.skip("stop hit before the time stop on this synthetic path")
    w.ex.prices["BTCUSDT"] = D(repr(round(float(feats["close"][i + 3]), 2)))
    await w.fire(feats.time(i + 3))
    assert await rt.store.get_position("BTCUSDT") is None
    assert w.ex.holding("BTC") == 0 and not any(o.status.is_open for o in w.ex.orders.values())
    async with w.sessions() as db:
        payloads = (await db.execute(select(RiskEvent.payload))).scalars().all()
    reasons = [p.get("reason") for p in payloads]
    assert "time_stop" in reasons


async def test_false_breakout_exit_when_price_closes_back_below_the_level(w: World) -> None:
    feats, i, rt = await _open_position(w)
    await set_plan(w, {"false_breakout": [str(D(10**6)), 5]})  # any close is below this level
    assert w.ex is not None
    w.ex.prices["BTCUSDT"] = D(repr(round(float(feats["close"][i + 1]), 2)))
    await w.fire(feats.time(i + 1))
    assert await rt.store.get_position("BTCUSDT") is None


async def test_kill_switch_in_the_database_flattens_the_account_and_latches_new_entries(
    w: World,
) -> None:
    _, _, rt = await _open_position(w)
    async with w.sessions.begin() as db:  # what POST /risk/kill does
        await db.execute(update(Bot).values(status=BotStatus.KILLED))
    await w.executor.tick()
    assert rt.breakers.kill_switch_active
    assert await rt.store.get_position("BTCUSDT") is None  # flattened
    assert w.ex is not None and w.ex.holding("BTC") == 0
    async with w.sessions() as db:
        kinds = set((await db.execute(select(RiskEvent.type))).scalars())
        statuses = set((await db.execute(select(Bot.status))).scalars())
    assert "KILL_SWITCH" in kinds and statuses == {BotStatus.KILLED}
    # a human resets it (2FA verified by the API): the runner releases its latch
    async with w.sessions.begin() as db:
        await db.execute(update(Bot).values(status=BotStatus.PAUSED))
    await w.executor.tick()
    assert not rt.breakers.kill_switch_active


async def test_tick_records_equity_snapshots_for_bot_accounts(w: World) -> None:
    await taken_signal(w)
    await w.executor.tick()
    assert await w.count(EquitySnapshot) == 1
    async with w.sessions() as db:
        snap = (await db.execute(select(EquitySnapshot))).scalar_one()
        acct = (await db.execute(select(ExchangeAccount.id))).scalar_one()
    assert snap.account_id == acct and snap.equity == D(10_000)


async def test_each_account_only_sees_its_own_orders_and_positions(w: World) -> None:
    _, _, rt = await _open_position(w)
    manual = PgExecutionStore(w.sessions)  # the API's own scope (account_id None)
    assert await manual.get_position("BTCUSDT") is None
    assert await manual.open_orders() == [] and await manual.open_positions() == []
    mine = rt.store
    assert await mine.get_position("BTCUSDT") is not None and await mine.open_orders()


async def test_trailing_stop_ratchets_to_highest_high_minus_atr_and_never_down(w: World) -> None:
    import numpy as np
    import pandas as pd

    from app.marketdata import indicators as ind

    feats, i, rt = await _open_position(w)
    mult, period = 1.0, 14  # tight enough to bite on the synthetic path
    await set_plan(w, {"trail": {"mult": mult, "period": period, "after_tp1": False}})
    assert w.ex is not None
    first = i + 1  # the entry bar
    atr = ind.atr(
        pd.Series(feats["high"]), pd.Series(feats["low"]), pd.Series(feats["close"]), period
    ).to_numpy()
    exercised = False  # a ratchet or a trail exit really happened (not a vacuous pass)
    for k in range(1, 8):
        price = D(repr(round(float(feats["close"][i + k]), 2)))
        w.ex.prices["BTCUSDT"] = price
        before = await rt.store.get_position("BTCUSDT")
        if before is None:
            break
        highest = max(float(before.avg_entry), float(np.max(feats["high"][first : i + k + 1])))
        level = D(repr(round(highest - float(atr[i + k]) * mult, 2)))
        await w.fire(feats.time(i + k))
        pos = await rt.store.get_position("BTCUSDT")
        if level > before.stop + D("0.02") and level >= price:
            assert pos is None  # a trail above the market is an exit, not an unplaceable stop
            exercised = True
            break
        if pos is None:  # the exchange-side stop itself was hit on this synthetic path
            break
        assert pos.stop >= before.stop and pos.protected  # never lower, never naked
        if level > before.stop + D("0.02"):
            assert abs(pos.stop - level) <= D("0.02"), (level, pos.stop)  # tick rounding
            exercised = True
    assert exercised
