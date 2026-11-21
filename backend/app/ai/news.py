"""News ingest (SPEC 4.3): RSS feeds -> ``news_items`` rows, deduplicated by URL.

Headlines are *untrusted text from the internet*. They are cleaned here (control characters,
length) and wrapped in data tags before any model sees them (``classify.py``); nothing in a
headline is ever treated as an instruction.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from time import struct_time
from typing import Any

import feedparser
import httpx
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.models import NewsItem

log = structlog.get_logger()
MAX_AGE = timedelta(hours=48)
_CONTROL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass(frozen=True, slots=True)
class RawNews:
    source: str
    url: str
    title: str
    published_at: datetime


def clean(text: str, limit: int = 300) -> str:
    return " ".join(_CONTROL.sub(" ", text).split())[:limit]


def _when(entry: Any) -> datetime | None:
    t: struct_time | None = entry.get("published_parsed") or entry.get("updated_parsed")
    return datetime(*t[:6], tzinfo=UTC) if t else None


def parse_feed(source: str, body: str, now: datetime) -> list[RawNews]:
    out = []
    for e in feedparser.parse(body).entries:
        url, title, when = str(e.get("link", "")), clean(str(e.get("title", ""))), _when(e)
        if not (url.startswith("http") and title and when) or now - when > MAX_AGE or when > now:
            continue
        out.append(RawNews(source, url, title, when))
    return out


def parse_feed_spec(spec: str) -> tuple[str, str]:
    name, _, url = spec.partition("|")
    return name.strip(), url.strip()


async def fetch_all(
    http: httpx.AsyncClient,
    feeds: list[str],
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
) -> list[RawNews]:
    items: list[RawNews] = []
    for spec in feeds:
        name, url = parse_feed_spec(spec)
        try:
            r = await http.get(url, timeout=10.0, follow_redirects=True)
            r.raise_for_status()
            items += parse_feed(name, r.text, now())
        except (httpx.HTTPError, ValueError) as e:  # one broken feed must not stop the others
            log.warning("news.feed_failed", source=name, error=type(e).__name__)
    return items


async def store_new(sessions: async_sessionmaker[AsyncSession], items: list[RawNews]) -> int:
    """Insert unseen headlines; returns how many were new."""
    if not items:
        return 0
    async with sessions.begin() as db:
        stmt = (
            pg_insert(NewsItem)
            .values(
                [
                    {
                        "source": i.source,
                        "url": i.url,
                        "title": i.title,
                        "published_at": i.published_at,
                    }
                    for i in items
                ]
            )
            .on_conflict_do_nothing(index_elements=["url"])
            .returning(NewsItem.id)
        )
        return len((await db.execute(stmt)).all())
