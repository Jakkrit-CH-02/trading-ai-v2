"""Entrypoint: ``python -m services.ai_worker``.

The only service that holds the Anthropic key. It holds no exchange keys and no encryption key, so
nothing a model returns can reach an order (SPEC 12). Loop: ingest headlines, classify them,
write a market brief per coin once per 4h bar (or sooner on a severe headline / user request).
"""

import asyncio
import json
from datetime import UTC, datetime, timedelta

import httpx
import structlog
from redis.asyncio import Redis
from sqlalchemy import select

from app.ai import brief as brief_mod
from app.ai.classify import classify_pending
from app.ai.llm import AnthropicLLM
from app.ai.news import fetch_all, store_new
from app.ai.service import AiService
from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.core.models import NewsItem
from app.marketdata.store import PgCandleStore
from app.notify.telegram import make_notifier

HEARTBEAT_KEY = "ai:heartbeat"
REFRESH_LIST = "ai:refresh"
NEWS_EVERY = timedelta(minutes=5)
SEVERE = 0.8  # a headline this serious triggers an early brief for the coins it mentions
SEVERE_COOLDOWN = timedelta(hours=1)
log = structlog.get_logger()


async def fear_greed(http: httpx.AsyncClient, url: str) -> int | None:
    try:
        r = await http.get(url, timeout=5.0)
        return int(r.json()["data"][0]["value"])
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError):
        return None


async def main() -> None:
    s = get_settings()
    configure_logging("ai-worker")
    key = s.anthropic_api_key.get_secret_value()
    engine = make_engine()
    sessions = make_session_factory(engine)
    redis: Redis = Redis.from_url(s.redis_url, decode_responses=True, socket_timeout=30)
    candles = PgCandleStore(sessions)
    http = httpx.AsyncClient()
    ai = (
        AiService(
            sessions,
            AnthropicLLM(key),
            budget_usd=s.ai_monthly_budget_usd,
            timeout_s=s.ai_timeout_s,
            notifier=make_notifier(s.telegram_bot_token.get_secret_value(), s.telegram_chat_id),
        )
        if key
        else None
    )
    if ai is None:
        log.warning("ai.disabled", reason="ANTHROPIC_API_KEY is not set: headlines only")
    last_news = datetime.min.replace(tzinfo=UTC)
    last_severe: dict[str, datetime] = {}
    log.info("ai_worker.started", enabled=ai is not None)
    while True:
        now = datetime.now(UTC)
        try:
            await redis.set(
                HEARTBEAT_KEY,
                json.dumps({"at": now.isoformat(), "enabled": ai is not None}),
                ex=120,
            )
            forced: set[str] = set()
            while (sym := await redis.lpop(REFRESH_LIST)) is not None:
                if sym in s.symbols:
                    forced.add(sym)
            if now - last_news >= NEWS_EVERY:
                last_news = now
                new = await store_new(sessions, await fetch_all(http, s.news_feeds))
                if ai is not None:
                    await classify_pending(ai, sessions, s.ai_news_model, s.symbols)
                    if new:
                        async with sessions() as db:
                            rows = (
                                await db.execute(
                                    select(NewsItem.symbols).where(
                                        NewsItem.severity >= SEVERE,
                                        NewsItem.published_at >= now - timedelta(minutes=30),
                                    )
                                )
                            ).scalars()
                            for syms in rows:
                                for base in syms:
                                    sym = f"{base}USDT"
                                    if (
                                        now - last_severe.get(sym, now - 2 * SEVERE_COOLDOWN)
                                        > SEVERE_COOLDOWN
                                    ):
                                        last_severe[sym] = now
                                        forced.add(sym)
            if ai is not None:
                fng = None
                for sym in s.symbols:
                    if sym in forced or await brief_mod.brief_due(sessions, sym, now):
                        fng = fng if fng is not None else await fear_greed(http, s.fng_url)
                        await brief_mod.generate_brief(
                            ai, sessions, candles, sym, s.ai_brief_model, now, fng
                        )
        except Exception:  # the worker never dies: the bots do not depend on it
            log.exception("ai_worker.cycle_failed")
        await asyncio.sleep(30)


if __name__ == "__main__":
    asyncio.run(main())
