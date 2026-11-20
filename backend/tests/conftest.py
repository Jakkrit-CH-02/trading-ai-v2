import asyncio
import os
from collections.abc import AsyncIterator

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.core.config import get_settings

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL")
needs_pg = pytest.mark.skipif(not TEST_DB_URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
async def pg_engine(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[AsyncEngine]:
    """A freshly migrated database (downgraded to base and upgraded again every time)."""
    assert TEST_DB_URL
    monkeypatch.setenv("DATABASE_URL", TEST_DB_URL)
    get_settings.cache_clear()
    cfg = Config("alembic.ini")
    await asyncio.to_thread(command.downgrade, cfg, "base")
    await asyncio.to_thread(command.upgrade, cfg, "head")
    eng = create_async_engine(TEST_DB_URL)
    yield eng
    await eng.dispose()
    get_settings.cache_clear()
