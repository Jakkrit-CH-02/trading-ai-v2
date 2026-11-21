"""The bot runner: closed candle in -> decision recorded.

Stage 1 (this module) judges and records signals. It places no orders yet; ``act`` is the
hook the execution layer plugs into."""

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.backtest.engine import BacktestConfig
from app.backtest.registry import default_params, make_strategy
from app.core.models import Bot, BotStatus, Decision, RiskEvent, StrategyConfig
from app.exchange.types import INTERVAL_MS
from app.marketdata.store import CandleStore
from app.runtime.frames import DataGap, load_features
from app.runtime.signals_store import in_cooldown, record_signal
from app.strategies.base import Strategy
from app.strategies.decision import BarDecision, decide_at_close

log = structlog.get_logger()
ACTIVE = (BotStatus.PAPER, BotStatus.RUNNING)
UNSUPPORTED = {"s4"}  # the grid is a different execution model; not run live yet


@dataclass(frozen=True, slots=True)
class BotSpec:
    id: uuid.UUID
    name: str
    strategy: str  # lower case: s1..s3
    params: dict[str, Any]
    symbols: tuple[str, ...]
    status: BotStatus
    account_id: uuid.UUID
    config_id: uuid.UUID


@dataclass(frozen=True, slots=True)
class Judged:
    bot: BotSpec
    symbol: str
    bar_open: datetime
    decision: BarDecision
    signal_id: uuid.UUID
    is_new: bool


async def load_active_bots(sessions: async_sessionmaker[AsyncSession]) -> list[BotSpec]:
    async with sessions() as db:
        rows = (
            await db.execute(
                select(Bot, StrategyConfig)
                .join(StrategyConfig, StrategyConfig.bot_id == Bot.id)
                .where(Bot.status.in_(ACTIVE), StrategyConfig.is_active.is_(True))
                .order_by(Bot.created_at, StrategyConfig.version.desc())
            )
        ).all()
    seen: set[uuid.UUID] = set()
    out: list[BotSpec] = []
    for bot, cfg in rows:  # newest active version of each bot
        if bot.id in seen:
            continue
        seen.add(bot.id)
        out.append(
            BotSpec(
                bot.id,
                bot.name,
                cfg.strategy.lower(),
                dict(cfg.params or {}),
                tuple(bot.symbols),
                BotStatus(bot.status),
                bot.account_id,
                cfg.id,
            )
        )
    return out


def build_strategy(name: str, params: dict[str, Any]) -> Strategy:
    """Config params are numbers; cast to each parameter's declared type like the API does."""
    defaults = default_params(name)
    overrides = {k: type(getattr(defaults, k))(v) for k, v in params.items()}
    s = make_strategy(name, overrides)
    return s  # type: ignore[return-value]  # S4 (grid) is excluded before this point


@dataclass
class BotRunner:
    sessions: async_sessionmaker[AsyncSession]
    candles: CandleStore
    config: BacktestConfig = field(default_factory=BacktestConfig)  # same defaults as backtest
    wait_for_htf_s: float = 90.0
    # a signal whose candle closed longer ago than this is recorded but not acted on (e.g. the
    # runner was down): entering late is not the trade the backtest measured
    max_signal_age_s: float = 300.0
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    act: Callable[[Judged], Awaitable[None]] | None = None
    _strategies: dict[uuid.UUID, Strategy] = field(default_factory=dict)

    def strategy_for(self, bot: BotSpec) -> Strategy:
        if bot.config_id not in self._strategies:
            self._strategies[bot.config_id] = build_strategy(bot.strategy, bot.params)
        return self._strategies[bot.config_id]

    async def _event(self, bot: BotSpec, type: str, severity: str, payload: dict[str, Any]) -> None:
        async with self.sessions.begin() as db:
            db.add(RiskEvent(bot_id=bot.id, type=type, severity=severity, payload=payload))

    async def on_candle_closed(
        self, symbol: str, interval: str, bar_open: datetime
    ) -> list[Judged]:
        """Called once per closed candle. Safe to call twice with the same candle."""
        out: list[Judged] = []
        for bot in await load_active_bots(self.sessions):
            if symbol not in bot.symbols:
                continue
            if bot.strategy in UNSUPPORTED:
                log.warning("runner.unsupported_strategy", bot=bot.name, strategy=bot.strategy)
                continue
            strat = self.strategy_for(bot)
            if strat.exec_interval != interval:
                continue
            judged = await self.judge(bot, strat, symbol, bar_open)
            if judged is None:
                continue
            out.append(judged)
            taken = judged.decision.decision == Decision.TAKEN
            if self.act is not None and judged.is_new and taken:  # only new, taken signals
                await self.act(judged)
        return out

    async def judge(
        self, bot: BotSpec, strat: Strategy, symbol: str, bar_open: datetime
    ) -> Judged | None:
        try:
            feats = await load_features(
                self.candles, strat, symbol, bar_open, wait_s=self.wait_for_htf_s
            )
        except DataGap as e:  # fail safe: no guess, no trade; the next bar tries again
            log.warning("runner.data_gap", bot=bot.name, symbol=symbol, error=str(e))
            await self._event(bot, "DATA_GAP", "warning", {"symbol": symbol, "detail": str(e)})
            return None
        i = len(feats) - 1
        cooling = await in_cooldown(
            self.sessions, bot.id, symbol, feats.time(i), self.config.cooldown_hours
        )
        bd = decide_at_close(
            strat, feats, i, self.config.weights, self.config.min_quote_volume_24h, cooling
        )
        if bd is None:
            return None
        age = self.now() - (bar_open + timedelta(milliseconds=INTERVAL_MS[strat.exec_interval]))
        if bd.decision == Decision.TAKEN and age.total_seconds() > self.max_signal_age_s:
            bd = replace(
                bd,
                decision=Decision.SKIPPED,
                reason=f"stale signal: candle closed {age.total_seconds():.0f}s ago",
            )
        sid, new = await record_signal(self.sessions, bot.id, bd)
        log.info(
            "runner.signal",
            bot=bot.name,
            symbol=symbol,
            decision=bd.decision.value,
            reason=bd.reason,
            new=new,
        )
        return Judged(bot, symbol, bar_open, bd, sid, new)
