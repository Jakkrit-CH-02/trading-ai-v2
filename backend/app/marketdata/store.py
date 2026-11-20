"""Candle persistence. ``CandleStore`` is a Protocol so the backfill/gap-fill logic can be
tested without a database (``InMemoryCandleStore``); production uses ``PgCandleStore``."""

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import Candle
from app.exchange.types import Kline

_BATCH = 1000  # 1000 rows x 11 columns stays under asyncpg's 32767 parameter limit


class CandleStore(Protocol):
    async def open_times(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> set[datetime]:
        """open_time of every stored candle in [start, end]."""

    async def save(self, klines: Sequence[Kline]) -> int:
        """Idempotently store closed candles; returns rows newly inserted."""

    async def load(self, symbol: str, interval: str, start: datetime, end: datetime) -> list[Kline]:
        """Closed candles in [start, end], ascending by open_time."""


class InMemoryCandleStore:
    def __init__(self) -> None:
        self.rows: dict[tuple[str, str, datetime], Kline] = {}

    async def open_times(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> set[datetime]:
        return {t for (s, i, t) in self.rows if s == symbol and i == interval and start <= t <= end}

    async def save(self, klines: Sequence[Kline]) -> int:
        new = 0
        for k in klines:
            if not k.is_closed:
                raise ValueError("refusing to store a candle that is still forming")
            key = (k.symbol, k.interval, k.open_time)
            if key not in self.rows:
                self.rows[key] = k
                new += 1
        return new

    async def load(self, symbol: str, interval: str, start: datetime, end: datetime) -> list[Kline]:
        rows = [
            k
            for (s, i, t), k in self.rows.items()
            if s == symbol and i == interval and start <= t <= end
        ]
        return sorted(rows, key=lambda k: k.open_time)


class PgCandleStore:
    def __init__(self, factory: async_sessionmaker[AsyncSession]) -> None:
        self._factory = factory

    async def open_times(
        self, symbol: str, interval: str, start: datetime, end: datetime
    ) -> set[datetime]:
        stmt = select(Candle.open_time).where(
            Candle.symbol == symbol,
            Candle.interval == interval,
            Candle.open_time >= start,
            Candle.open_time <= end,
        )
        async with self._factory() as session:
            return set((await session.scalars(stmt)).all())

    async def save(self, klines: Sequence[Kline]) -> int:
        if any(not k.is_closed for k in klines):
            raise ValueError("refusing to store a candle that is still forming")
        inserted = 0
        async with self._factory() as session, session.begin():
            for i in range(0, len(klines), _BATCH):
                rows = [
                    {
                        "symbol": k.symbol,
                        "interval": k.interval,
                        "open_time": k.open_time,
                        "o": k.o,
                        "h": k.h,
                        "l": k.l,
                        "c": k.c,
                        "v": k.v,
                        "quote_v": k.quote_v,
                        "trades": k.trades,
                        "taker_buy_v": k.taker_buy_v,
                    }
                    for k in klines[i : i + _BATCH]
                ]
                stmt = (
                    pg_insert(Candle)
                    .values(rows)
                    .on_conflict_do_nothing(index_elements=["symbol", "interval", "open_time"])
                    .returning(Candle.open_time)
                )
                inserted += len((await session.execute(stmt)).all())
        return inserted

    async def load(self, symbol: str, interval: str, start: datetime, end: datetime) -> list[Kline]:
        stmt = (
            select(Candle)
            .where(
                Candle.symbol == symbol,
                Candle.interval == interval,
                Candle.open_time >= start,
                Candle.open_time <= end,
            )
            .order_by(Candle.open_time)
        )
        async with self._factory() as session:
            rows = (await session.scalars(stmt)).all()
        return [
            Kline(
                symbol=r.symbol,
                interval=r.interval,
                open_time=r.open_time,
                o=r.o,
                h=r.h,
                l=r.l,
                c=r.c,
                v=r.v,
                quote_v=r.quote_v,
                trades=r.trades,
                taker_buy_v=r.taker_buy_v,
            )
            for r in rows
        ]
