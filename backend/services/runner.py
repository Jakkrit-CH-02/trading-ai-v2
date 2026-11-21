"""Entrypoint: ``python -m services.runner``.

Consumes the ``candles.closed`` Redis stream (consumer group, so a crash loses nothing: unacked
messages are re-read on restart) and hands each closed candle to the BotRunner."""

import asyncio
import contextlib
from datetime import UTC, datetime
from typing import Any

import structlog
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.exchange.types import ms_to_dt
from app.execution.pg_store import PgExecutionStore
from app.marketdata.publisher import STREAM
from app.marketdata.store import PgCandleStore
from app.notify.telegram import make_notifier
from app.runtime.accounts import AccountPool, binance_adapter_factory
from app.runtime.executor import Executor
from app.runtime.runner import BotRunner

GROUP = "runner"
CONSUMER = "runner-1"
HEARTBEAT_KEY = "runner:heartbeat"
log = structlog.get_logger()


async def heartbeat(redis: Redis, every_s: float = 10.0) -> None:
    while True:
        await redis.set(HEARTBEAT_KEY, datetime.now(UTC).isoformat(), ex=int(every_s * 4))
        await asyncio.sleep(every_s)


async def supervise(executor: Executor, every_s: float = 5.0) -> None:
    """Kill switch, equity snapshots and reconcilers: independent of candle traffic."""
    while True:
        try:
            await executor.tick()
        except Exception:
            log.exception("runner.tick_failed")
        await asyncio.sleep(every_s)


async def handle(
    runner: BotRunner, executor: Executor, redis: Redis, msg_id: str, fields: dict[str, str]
) -> None:
    try:
        symbol, interval = fields["symbol"], fields["interval"]
        bar = ms_to_dt(int(fields["open_time"]))
        await executor.manage(symbol, interval, bar)  # existing positions first (as backtest)
        await runner.on_candle_closed(symbol, interval, bar)  # then new entries
    except Exception:  # never let one bad candle stop the loop; it stays pending for a retry
        log.exception("runner.candle_failed", id=msg_id, fields=fields)
        return
    await redis.xack(STREAM, GROUP, msg_id)


async def main() -> None:
    s = get_settings()
    configure_logging("runner")
    engine = make_engine()
    sessions = make_session_factory(engine)
    # the socket timeout must outlast the 5 s blocking read, or every idle read "times out"
    redis: Redis = Redis.from_url(s.redis_url, decode_responses=True, socket_timeout=30)
    with contextlib.suppress(Exception):  # BUSYGROUP: it already exists
        await redis.xgroup_create(STREAM, GROUP, id="$", mkstream=True)
    candles = PgCandleStore(sessions)
    pool = AccountPool(sessions, PgExecutionStore(sessions), binance_adapter_factory(s))
    executor = Executor(
        sessions,
        pool,
        candles,
        s.symbols,
        notifier=make_notifier(s.telegram_bot_token.get_secret_value(), s.telegram_chat_id),
    )
    runner = BotRunner(sessions, candles, act=executor.act)
    beat = asyncio.create_task(heartbeat(redis))
    supervisor = asyncio.create_task(supervise(executor))
    log.info("runner.started")
    try:
        cursor = "0"  # first drain what a previous run left unacknowledged, then go live
        while True:
            try:
                resp: Any = await redis.xreadgroup(
                    GROUP,
                    CONSUMER,
                    {STREAM: cursor},
                    count=20,
                    block=5000 if cursor == ">" else None,
                )
            except (RedisError, OSError):  # Redis restarting / network blip: retry, do not die
                log.exception("runner.redis_unavailable")
                await asyncio.sleep(2)
                continue
            batch: list[tuple[str, dict[str, str]]] = resp[0][1] if resp else []
            if cursor == "0" and not batch:
                cursor = ">"
                continue
            for msg_id, fields in batch:
                await handle(runner, executor, redis, msg_id, fields)
            if cursor == "0" and batch:
                cursor = batch[-1][0]  # keep draining pending messages, in order
    finally:
        for task in (beat, supervisor):
            task.cancel()
        for task in (beat, supervisor):
            with contextlib.suppress(asyncio.CancelledError):
                await task
        await executor.aclose()
        await redis.aclose()
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
