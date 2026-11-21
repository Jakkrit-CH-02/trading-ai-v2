"""Entrypoint: ``python -m services.ml_worker``.

Keeps S_ml honest (SPEC 4.1): every Monday retrain each strategy on the rolling data and promote
only if the new model earns it; every day check the active models for feature drift and live
precision and switch them off if they degrade. No exchange keys, no LLM key: candles in, scores out.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis

from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.marketdata.store import PgCandleStore
from app.ml.pipeline import monitor_model, retrain_due, train_and_register
from app.ml.train import TrainConfig

HEARTBEAT_KEY = "ml:heartbeat"
STRATEGIES = ["s1", "s2"]  # S3 has too few signals; S4 (grid) has no entry signal to learn from
TRAIN_YEARS = 3.0  # SPEC says 12 months, but S1-S2 have too few signals in a year to learn from
RETRAIN_EVERY = timedelta(days=7)
MONITOR_EVERY = timedelta(days=1)
log = structlog.get_logger()


async def main() -> None:
    s = get_settings()
    configure_logging("ml-worker")
    engine = make_engine()
    sessions = make_session_factory(engine)
    store = PgCandleStore(sessions)
    redis: Redis = Redis.from_url(s.redis_url, decode_responses=True)
    last_monitor = datetime.min.replace(tzinfo=UTC)
    log.info("ml_worker.started")
    while True:
        now = datetime.now(UTC)
        try:
            await redis.set(HEARTBEAT_KEY, now.isoformat(), ex=300)
            if now - last_monitor >= MONITOR_EVERY:
                last_monitor = now
                for name in STRATEGIES:
                    m = await monitor_model(sessions, store, name, s.symbols, now)
                    log.info("ml.monitor", strategy=name, suspended=m.suspended, reason=m.reason)
            for name in STRATEGIES:
                if not await retrain_due(sessions, name, now, RETRAIN_EVERY):
                    continue
                attempt = f"ml:last_attempt:{name}"  # also covers "too few signals": no row exists
                if not await redis.set(
                    attempt, now.isoformat(), nx=True, ex=int(RETRAIN_EVERY.total_seconds())
                ):
                    continue
                try:
                    r = await train_and_register(
                        sessions, store, name, s.symbols, TRAIN_YEARS, TrainConfig(), now
                    )
                    log.info("ml.trained", strategy=name, version=r.version,
                             promoted=r.promoted, reason=r.reason)  # fmt: skip
                except ValueError as e:  # too few signals in the window: nothing to learn
                    log.info("ml.skipped", strategy=name, reason=str(e))
        except Exception:  # never die: the bots do not depend on this worker
            log.exception("ml_worker.cycle_failed")
        await asyncio.sleep(300)


if __name__ == "__main__":
    asyncio.run(main())
