"""BotRunner against a real database: a closed candle becomes exactly one recorded decision."""

import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.backtest.engine import BacktestConfig
from app.core.db import make_session_factory
from app.core.models import (
    Bot,
    BotMode,
    BotStatus,
    Decision,
    ExchangeAccount,
    Market,
    Position,
    PositionStatus,
    RiskEvent,
    RiskProfile,
    Side,
    StrategyConfig,
    Trade,
    User,
)
from app.core.models import Signal as SignalRow
from app.exchange.types import INTERVAL_MS
from app.marketdata.store import InMemoryCandleStore
from app.runtime.plan import ExitPlan
from app.runtime.runner import BotRunner, Judged, build_strategy
from app.strategies.base import MarketFrames
from app.strategies.decision import decide_at_close
from tests.conftest import needs_pg
from tests.synth import standard_market, to_4h
from tests.test_runtime_parity import klines

pytestmark = needs_pg
# synthetic volumes are tiny: switch the liquidity filter off so signals can be TAKEN
CFG = BacktestConfig(min_quote_volume_24h=0.0)


async def make_bot(
    sessions: async_sessionmaker[AsyncSession],
    strategy: str = "S1",
    status: BotStatus = BotStatus.PAPER,
    symbols: tuple[str, ...] = ("BTCUSDT",),
    params: dict[str, Any] | None = None,
) -> uuid.UUID:
    async with sessions.begin() as db:
        user = User(email=f"{uuid.uuid4().hex[:8]}@x.io", password_hash="x")
        db.add(user)
        await db.flush()
        acct = ExchangeAccount(user_id=user.id, label="demo", api_key_enc=b"k", api_secret_enc=b"s")
        prof = RiskProfile(name=uuid.uuid4().hex[:8])
        db.add_all([acct, prof])
        await db.flush()
        bot = Bot(
            account_id=acct.id,
            name="Alpha",
            market=Market.SPOT,
            symbols=list(symbols),
            status=status,
            mode=BotMode.PAPER,
            risk_profile_id=prof.id,
        )
        db.add(bot)
        await db.flush()
        db.add(StrategyConfig(bot_id=bot.id, strategy=strategy, params=params or {}, version=1))
        return bot.id


class Env:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self.sessions = sessions
        self.candles = InMemoryCandleStore()
        self.acted: list[Judged] = []

        async def act(j: Judged) -> None:
            self.acted.append(j)

        self.t = datetime(2030, 1, 1, tzinfo=UTC)
        self.runner = BotRunner(
            sessions, self.candles, CFG, wait_for_htf_s=0.0, act=act, now=lambda: self.t
        )

    async def fire(self, symbol: str, interval: str, bar: datetime, late_s: float = 10) -> Any:
        """The candle closes ``late_s`` seconds ago (the normal case: the stream is prompt)."""
        self.t = bar + timedelta(milliseconds=INTERVAL_MS[interval]) + timedelta(seconds=late_s)
        return await self.runner.on_candle_closed(symbol, interval, bar)


@pytest.fixture
async def env(pg_engine: AsyncEngine) -> AsyncIterator[Env]:
    yield Env(make_session_factory(pg_engine))


async def load_market(env: Env) -> tuple[Any, int]:
    """Candles for a synthetic market, plus the index of a bar where S1 takes a signal."""
    df = standard_market()
    await env.candles.save(klines(df, "BTCUSDT", "1h") + klines(to_4h(df), "BTCUSDT", "4h"))
    strat = build_strategy("s1", {})
    feats = strat.prepare(MarketFrames("BTCUSDT", {"1h": df, "4h": to_4h(df)}, None))
    for i in range(2500, len(feats)):
        bd = decide_at_close(strat, feats, i, CFG.weights, CFG.min_quote_volume_24h, False)
        if bd is not None and bd.decision == Decision.TAKEN:
            return feats, i
    raise AssertionError("no TAKEN signal in the synthetic market")


async def n_signals(env: Env) -> int:
    async with env.sessions() as db:
        return int((await db.execute(select(func.count()).select_from(SignalRow))).scalar_one())


async def test_a_closed_candle_records_one_decision_with_its_exit_plan(env: Env) -> None:
    bot_id = await make_bot(env.sessions)
    feats, i = await load_market(env)
    bar = feats.time(i)

    out = await env.fire("BTCUSDT", "1h", bar)
    assert len(out) == 1 and out[0].is_new and out[0].decision.decision == Decision.TAKEN
    async with env.sessions() as db:
        row = (await db.execute(select(SignalRow))).scalar_one()
    assert row.bot_id == bot_id and row.bar_time == bar and row.decision == Decision.TAKEN
    assert row.side == Side.BUY and row.stop < row.entry and row.score is not None
    plan = ExitPlan.from_json(row.exit_plan)
    assert plan.trail is not None and plan.trail.after_tp1  # S1 trails the runner after TP1
    assert row.reasons  # explainability: why the strategy fired
    assert env.acted == out  # the execution hook is called for a new signal


async def test_replaying_the_same_candle_never_fires_twice(env: Env) -> None:
    await make_bot(env.sessions)
    feats, i = await load_market(env)
    bar = feats.time(i)
    first = await env.fire("BTCUSDT", "1h", bar)
    again = await env.fire("BTCUSDT", "1h", bar)  # redelivered by the stream
    assert first[0].signal_id == again[0].signal_id and not again[0].is_new
    assert await n_signals(env) == 1 and len(env.acted) == 1


@pytest.mark.parametrize(
    ("status", "strategy"),
    [
        (BotStatus.DRAFT, "S1"),
        (BotStatus.PAUSED, "S1"),
        (BotStatus.KILLED, "S1"),
        (BotStatus.PAPER, "S4"),  # the grid is not run live
    ],
)
async def test_only_active_supported_bots_are_judged(
    env: Env, status: BotStatus, strategy: str
) -> None:
    await make_bot(env.sessions, strategy=strategy, status=status)
    feats, i = await load_market(env)
    assert await env.fire("BTCUSDT", "1h", feats.time(i)) == []
    assert await n_signals(env) == 0


async def test_other_symbols_and_other_timeframes_are_ignored(env: Env) -> None:
    await make_bot(env.sessions, symbols=("ETHUSDT",))
    feats, i = await load_market(env)
    assert await env.fire("BTCUSDT", "1h", feats.time(i)) == []
    await make_bot(env.sessions)  # a BTC bot, but the candle is a 4h one (S1 executes on 1h)
    assert await env.fire("BTCUSDT", "4h", feats.time(i)) == []
    assert await n_signals(env) == 0


async def test_a_data_gap_records_an_event_and_no_signal(env: Env) -> None:
    bot_id = await make_bot(env.sessions)
    feats, i = await load_market(env)
    missing = feats.time(i) + timedelta(days=400)  # nothing stored for that bar
    assert await env.fire("BTCUSDT", "1h", missing) == []
    async with env.sessions() as db:
        ev = (await db.execute(select(RiskEvent))).scalar_one()
    assert ev.type == "DATA_GAP" and ev.bot_id == bot_id and await n_signals(env) == 0


async def test_a_recent_losing_stop_puts_the_symbol_in_cooldown(env: Env) -> None:
    bot_id = await make_bot(env.sessions)
    feats, i = await load_market(env)
    bar = feats.time(i)
    async with env.sessions.begin() as db:
        pos = Position(
            bot_id=bot_id,
            symbol="BTCUSDT",
            side=Side.BUY,
            qty=Decimal(1),
            avg_entry=Decimal(100),
            status=PositionStatus.CLOSED,
            opened_at=bar - timedelta(hours=5),
            closed_at=bar - timedelta(hours=1),
        )
        db.add(pos)
        await db.flush()
        db.add(
            Trade(
                position_id=pos.id,
                pnl_usdt=Decimal(-10),
                pnl_r=Decimal(-1),
                fees=Decimal(0),
                slippage=Decimal(0),
                holding_minutes=240,
                exit_reason="stop",
            )
        )
    out = await env.fire("BTCUSDT", "1h", bar)
    assert out[0].decision.decision == Decision.REJECTED
    assert out[0].decision.reason == "cooldown after stop"
    assert env.acted == []  # a rejected signal is recorded but never acted on


async def test_the_decision_equals_the_backtest_decision(env: Env) -> None:
    await make_bot(env.sessions)
    feats, i = await load_market(env)
    strat = build_strategy("s1", {})
    want = decide_at_close(strat, feats, i, CFG.weights, CFG.min_quote_volume_24h, False)
    out = await env.fire("BTCUSDT", "1h", feats.time(i))
    assert want is not None and out[0].decision == want


def test_params_from_a_bot_config_are_cast_to_the_declared_types() -> None:
    s = build_strategy("s1", {"rsi_period": 10.0, "tp1_r": 1.8})
    assert s.p.rsi_period == 10 and isinstance(s.p.rsi_period, int) and s.p.tp1_r == 1.8  # type: ignore[attr-defined]


async def test_a_signal_for_a_candle_that_closed_long_ago_is_recorded_but_not_acted_on(
    env: Env,
) -> None:
    await make_bot(env.sessions)
    feats, i = await load_market(env)
    out = await env.fire("BTCUSDT", "1h", feats.time(i), late_s=3600)  # runner was down an hour
    assert out[0].decision.decision == Decision.SKIPPED
    assert out[0].decision.reason.startswith("stale signal") and env.acted == []
    assert await n_signals(env) == 1  # still explainable afterwards
