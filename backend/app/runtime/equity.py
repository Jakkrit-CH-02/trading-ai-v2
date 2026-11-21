"""Equity snapshots: day/week baselines and the peak survive restarts (they used to live in
memory), and drive the daily/weekly loss and drawdown breakers."""

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import EquitySnapshot
from app.risk.types import PortfolioState

ZERO = Decimal(0)


def day_start_of(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)


def week_start_of(now: datetime) -> datetime:
    return day_start_of(now) - timedelta(days=now.astimezone(UTC).weekday())


async def baselines(
    sessions: async_sessionmaker[AsyncSession], account_id: uuid.UUID | None, now: datetime
) -> tuple[Decimal | None, Decimal | None, Decimal | None]:
    """(equity at 00:00 UTC today, at Monday 00:00 UTC, all-time peak); ``None`` = unknown."""
    if account_id is None:
        return None, None, None

    async def first_since(db: AsyncSession, since: datetime) -> Decimal | None:
        q = (
            select(EquitySnapshot.equity)
            .where(EquitySnapshot.account_id == account_id, EquitySnapshot.ts >= since)
            .order_by(EquitySnapshot.ts)
            .limit(1)
        )
        return (await db.execute(q)).scalar_one_or_none()

    async with sessions() as db:
        day = await first_since(db, day_start_of(now))
        week = await first_since(db, week_start_of(now))
        peak = (
            await db.execute(
                select(func.max(EquitySnapshot.equity)).where(
                    EquitySnapshot.account_id == account_id
                )
            )
        ).scalar_one()
    return day, week, peak


async def record_snapshot(
    sessions: async_sessionmaker[AsyncSession],
    account_id: uuid.UUID | None,
    now: datetime,
    pf: PortfolioState,
) -> None:
    if account_id is None:
        return
    dd = (pf.peak_equity - pf.equity) / pf.peak_equity if pf.peak_equity > 0 else ZERO
    stmt = (
        pg_insert(EquitySnapshot)
        .values(
            account_id=account_id,
            ts=now.replace(second=0, microsecond=0),
            equity=pf.equity,
            cash=pf.cash,
            exposure=pf.total_exposure,
            drawdown=dd,
        )
        .on_conflict_do_nothing(index_elements=["account_id", "ts"])
    )
    async with sessions.begin() as db:
        await db.execute(stmt)
