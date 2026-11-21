"""Persist every decision (SPEC 1.5: signals table keeps taken, skipped and rejected ones)."""

import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import Decision, Position, Side, Trade
from app.core.models import Signal as SignalRow
from app.runtime.plan import ExitPlan, jsonable
from app.strategies.decision import BarDecision

COOLDOWN_REASONS = ("stop", "emergency_close")


def _d(x: float | Decimal | None) -> Decimal | None:
    return None if x is None else Decimal(repr(round(float(x), 6)))


async def record_signal(
    sessions: async_sessionmaker[AsyncSession], bot_id: uuid.UUID, bd: BarDecision
) -> tuple[uuid.UUID, bool]:
    """Insert the decision; returns ``(signal id, is_new)``. Replaying the same bar finds the
    existing row (unique per bot, symbol, strategy and bar) and reports ``is_new=False``."""
    sig = bd.signal
    values = {
        "bot_id": bot_id,
        "symbol": sig.symbol,
        "strategy": sig.strategy,
        "side": Side.BUY,
        "entry": sig.entry,
        "stop": sig.stop,
        "tp1": sig.tp1,
        "s_tech": _d(bd.score.s_tech),
        "s_ml": _d(bd.score.s_ml),
        "s_ai": _d(bd.score.s_ai),
        "score": _d(bd.score.score),
        "decision": bd.decision,
        "reject_reason": bd.reason or None,
        "bar_time": sig.bar_time,
        "exit_plan": ExitPlan.of(sig).to_json(),
        "reasons": jsonable(sig.reasons),
    }
    async with sessions.begin() as db:
        got = (
            await db.execute(
                pg_insert(SignalRow)
                .values(**values)
                .on_conflict_do_nothing(constraint="uq_signal_bar")
                .returning(SignalRow.id)
            )
        ).scalar_one_or_none()
        if got is not None:
            return got, True
        existing = (
            await db.execute(
                select(SignalRow.id).where(
                    SignalRow.bot_id == bot_id,
                    SignalRow.symbol == sig.symbol,
                    SignalRow.strategy == sig.strategy,
                    SignalRow.bar_time == sig.bar_time,
                )
            )
        ).scalar_one()
        return existing, False


async def in_cooldown(
    sessions: async_sessionmaker[AsyncSession],
    bot_id: uuid.UUID,
    symbol: str,
    now: datetime,
    hours: int,
) -> bool:
    """A losing stop blocks re-entry for ``hours`` (SPEC 2.4). Read from the database so a
    restart does not forget it."""
    q = (
        select(func.count())
        .select_from(Trade)
        .join(Position, Position.id == Trade.position_id)
        .where(
            Position.bot_id == bot_id,
            Position.symbol == symbol,
            Trade.pnl_usdt < 0,
            Trade.exit_reason.in_(COOLDOWN_REASONS),
            Position.closed_at > now - timedelta(hours=hours),
        )
    )
    async with sessions() as db:
        return bool((await db.execute(q)).scalar_one())


async def update_outcome(
    sessions: async_sessionmaker[AsyncSession],
    signal_id: uuid.UUID,
    reason: str,
    decision: Decision | None = None,
) -> None:
    """What happened to a TAKEN signal after the Risk Engine / exchange had their say."""
    values: dict[str, object] = {"reject_reason": reason[:1000]}
    if decision is not None:
        values["decision"] = decision
    async with sessions.begin() as db:
        await db.execute(update(SignalRow).where(SignalRow.id == signal_id).values(**values))
