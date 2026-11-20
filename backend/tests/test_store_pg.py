"""PgCandleStore against a real TimescaleDB. Needs TEST_DATABASE_URL (see test_migrations)."""

import asyncio
import os
from collections.abc import AsyncIterator
from decimal import Decimal

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings
from app.core.db import make_session_factory
from app.exchange.simulated import SimulatedExchangeAdapter
from app.marketdata.backfill import fill_gaps
from app.marketdata.store import PgCandleStore
from tests.helpers import at, make_kline

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
async def engine(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    assert URL
    monkeypatch.setenv("DATABASE_URL", URL)
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    # alembic/env.py calls asyncio.run(), so it must not run on this loop's thread
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    eng = create_async_engine(URL)
    yield eng
    await eng.dispose()
    get_settings.cache_clear()


async def test_save_is_idempotent_and_exact(engine: AsyncEngine) -> None:
    store = PgCandleStore(make_session_factory(engine))
    batch = [make_kline(i) for i in range(5)]
    assert await store.save(batch) == 5
    assert await store.save(batch) == 0  # replay inserts nothing
    assert await store.open_times("BTCUSDT", "1h", at(0), at(10)) == {at(i) for i in range(5)}
    async with engine.connect() as conn:
        c = (
            await conn.execute(text("SELECT c FROM candles WHERE open_time = :t"), {"t": at(2)})
        ).scalar_one()
    assert c == Decimal("102.5000000000")  # NUMERIC, no float rounding


async def test_forming_candle_rejected(engine: AsyncEngine) -> None:
    with pytest.raises(ValueError, match="forming"):
        await PgCandleStore(make_session_factory(engine)).save([make_kline(0, closed=False)])


async def test_backfill_through_postgres_resumes(engine: AsyncEngine) -> None:
    store = PgCandleStore(make_session_factory(engine))
    adapter = SimulatedExchangeAdapter([make_kline(i) for i in range(30)], now=at(30))
    await store.save([make_kline(i) for i in range(10)])  # an interrupted earlier run
    res = await fill_gaps(adapter, store, "BTCUSDT", "1h", at(0))
    assert (res.missing, res.inserted, res.unavailable) == (20, 20, 0)
