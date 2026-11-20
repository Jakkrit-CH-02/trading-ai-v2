"""Migration tests against a real TimescaleDB. Skipped unless TEST_DATABASE_URL is set.

Example: TEST_DATABASE_URL=postgresql+asyncpg://softtrade:test@127.0.0.1:55432/softtrade
"""

import asyncio
import os
from collections.abc import Iterator
from typing import Any

import asyncpg
import pytest
from alembic import command
from alembic.config import Config

from app.core.config import get_settings

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


def _dsn() -> str:
    assert URL
    return URL.replace("+asyncpg", "")


@pytest.fixture
def alembic_cfg(monkeypatch: pytest.MonkeyPatch) -> Iterator[Config]:
    assert URL
    monkeypatch.setenv("DATABASE_URL", URL)
    get_settings.cache_clear()
    yield Config("alembic.ini")
    get_settings.cache_clear()


async def _fetch(sql: str) -> list[Any]:
    conn = await asyncpg.connect(_dsn())
    try:
        rows: list[Any] = list(await conn.fetch(sql))
        return rows
    finally:
        await conn.close()


async def _execute(sql: str) -> None:
    conn = await asyncpg.connect(_dsn())
    try:
        await conn.execute(sql)
    finally:
        await conn.close()


def test_upgrade_downgrade_upgrade(alembic_cfg: Config) -> None:
    command.downgrade(alembic_cfg, "base")
    command.upgrade(alembic_cfg, "head")
    rows = asyncio.run(_fetch("SELECT hypertable_name FROM timescaledb_information.hypertables"))
    assert {r["hypertable_name"] for r in rows} == {
        "candles",
        "market_metrics",
        "equity_snapshots",
    }
    command.downgrade(alembic_cfg, "base")
    tables = asyncio.run(_fetch("SELECT 1 FROM pg_tables WHERE tablename = 'candles'"))
    assert tables == []
    command.upgrade(alembic_cfg, "head")


def test_money_columns_are_numeric_never_float(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "head")
    rows = asyncio.run(
        _fetch(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND data_type IN ('double precision','real')"
        )
    )
    assert rows == []


def test_audit_log_is_append_only(alembic_cfg: Config) -> None:
    command.upgrade(alembic_cfg, "head")
    asyncio.run(_execute("DELETE FROM audit_log"))  # empty table: trigger is per-row, no-op
    asyncio.run(_execute("INSERT INTO audit_log (action, target) VALUES ('test', 't')"))
    with pytest.raises(asyncpg.RaiseError, match="append-only"):
        asyncio.run(_execute("UPDATE audit_log SET action = 'x'"))
    with pytest.raises(asyncpg.RaiseError, match="append-only"):
        asyncio.run(_execute("DELETE FROM audit_log"))
