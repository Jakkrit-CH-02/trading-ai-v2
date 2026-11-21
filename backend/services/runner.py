"""Entrypoint: ``python -m services.runner``.

Consumes the ``candles.closed`` Redis stream (consumer group, so a crash loses nothing: unacked
messages are re-read on restart) and hands each closed candle to the BotRunner."""

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.exchange.types import ms_to_dt
from app.marketdata.publisher import STREAM
from app.marketdata.store import PgCandleStore
from app.runtime.runner import BotRunner

GROUP = "runner"
CONSUMER = "runner-1"
HEARTBEAT_KEY = "runner:heartbeat"
log = structlog.get_logger()


async def heartbeat(redis: Redis, every_s: float = 10.0) -> None:
    while True:
        await redis.set(HEARTBEAT_KEY, datetime.now(UTC).isoformat(), ex=int(every_s * 4))
        await asyncio.sleep(every_s)


async def handle(runner: BotRunner, redis: Redis, msg_id: str, fields: dict[str, str]) -> None:
    try:
        await runner.on_candle_closed(
            fields["symbol"], fields["interval"], ms_to_dt(int(fields["open_time"]))
        )
    except Exception:  # never let one bad candle stop the loop; it stays pending for a retry
        log.exception("runner.candle_failed", id=msg_id, fields=fields)
        return
    await redis.xack(STREAM, GROUP, msg_id)


async def main() -> None:
    s = get_settings()
    configure_logging("runner")
    engine = make_engine()
    sessions = make_session_factory(engine)
    redis: Redis = Redis.from_url(s.redis_url, decode_responses=True)
    with contextlib.suppress(Exception):  # BUSYGROUP: it already exists
        await redis.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    runner = BotRunner(sessions, PgCandleStore(sessions))
    beat = asyncio.create_task(heartbeat(redis))
    log.info("runner.started")
    try:
        cursor = "0"  # first drain what a previous run left unacknowledged, then go live
        while True:
            resp: Any = await redis.xreadgroup(
                GROUP, CONSUMER, {STREAM: cursor}, count=20, block=5000 if cursor == ">" else None
            )
            batch: list[tuple[str, dict[str, str]]] = resp[0][1] if resp else []
            if cursor == "0" and not batch:
                cursor = ">"
                continue
            for msg_id, fields in batch:
                await handle(runner, redis, msg_id, fields)
            if cursor == "0" and batch:
                cursor = batch[-1][0]  # keep draining pending messages, in order
    finally:
        beat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await beat
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
