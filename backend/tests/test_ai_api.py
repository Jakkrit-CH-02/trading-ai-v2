"""AI Analyst endpoints: briefs, headlines, status and the rate-limited refresh."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

from app.core.models import AiAnalysis, AnalysisKind, NewsItem
from app.main import create_app
from tests.conftest import needs_pg
from tests.test_bots_api import Env, env  # noqa: F401  (fixture)

pytestmark = needs_pg


class FakeRedis:
    def __init__(self, beat: dict[str, Any] | None = None) -> None:
        self.beat = beat
        self.keys: set[str] = set()
        self.queue: list[str] = []

    async def get(self, key: str) -> str | None:
        assert key == "ai:heartbeat"
        return None if self.beat is None else json.dumps(self.beat)

    async def set(self, key: str, value: str, ex: int, nx: bool) -> bool | None:
        if nx and key in self.keys:
            return None
        self.keys.add(key)
        return True

    async def rpush(self, key: str, value: str) -> None:
        assert key == "ai:refresh"
        self.queue.append(value)


def n(
    url: str, title: str, at: datetime, syms: list[str], sent: str, sev: str, cat: str
) -> NewsItem:
    return NewsItem(
        source="A", url=url, title=title, published_at=at, symbols=syms,
        sentiment=Decimal(sent), severity=Decimal(sev), category=cat,
    )  # fmt: skip


def brief_row(symbol: str, minutes_ago: int, **out: Any) -> AiAnalysis:
    body = {"bias": "bull", "s_ai": 70, "support": [1.0], "resistance": [2.0], "risks": ["r"],
            "summary_th": ["a", "b", "c"], **out}  # fmt: skip
    return AiAnalysis(
        kind=AnalysisKind.BRIEF, symbol=symbol, model="claude-sonnet-5-5", prompt_hash="h",
        input={}, output=body, cost_usd=Decimal("0.01"),
        created_at=datetime.now(UTC) - timedelta(minutes=minutes_ago),
    )  # fmt: skip


async def test_briefs_list_the_newest_per_coin_and_skip_failed_calls(env: Env) -> None:  # noqa: F811
    assert env.svc.db
    async with env.svc.db.begin() as db:
        db.add_all([
            brief_row("BTCUSDT", 300, s_ai=40, bias="bear"),
            brief_row("BTCUSDT", 10, s_ai=80),
            brief_row("ETHUSDT", 20),
            AiAnalysis(kind=AnalysisKind.BRIEF, symbol="SOLUSDT", model="m", prompt_hash="h",
                       input={}, output={"error": "timeout"}),
            AiAnalysis(kind=AnalysisKind.NEWS, model="m", prompt_hash="h", input={}, output={}),
        ])  # fmt: skip
    latest = (await env.c.get("/api/v1/ai/briefs")).json()
    assert [(b["symbol"], b["s_ai"]) for b in latest] == [("BTCUSDT", 80), ("ETHUSDT", 70)]
    hist = (await env.c.get("/api/v1/ai/briefs?symbol=BTCUSDT")).json()
    assert [b["s_ai"] for b in hist] == [80, 40]  # history of one coin, newest first
    assert (await env.c.get("/api/v1/ai/briefs?symbol=SOLUSDT")).json() == []


async def test_a_malformed_stored_brief_is_hidden_not_a_500(env: Env) -> None:  # noqa: F811
    assert env.svc.db
    async with env.svc.db.begin() as db:
        db.add(brief_row("BTCUSDT", 1, bias="sideways"))
    assert (await env.c.get("/api/v1/ai/briefs")).json() == []


async def test_news_is_listed_newest_first_and_filtered_by_coin(env: Env) -> None:  # noqa: F811
    assert env.svc.db
    now = datetime.now(UTC)
    async with env.svc.db.begin() as db:
        db.add_all([
            n("https://a/1", "old btc", now - timedelta(hours=3), ["BTC"], "0.5", "0.2", "market"),
            n("https://a/2", "new eth", now, ["ETH"], "-0.5", "0.9", "hack"),
            NewsItem(source="B", url="https://b/3", title="unclassified",
                     published_at=now - timedelta(hours=1)),
        ])  # fmt: skip
    allnews = (await env.c.get("/api/v1/ai/news")).json()
    assert [n["title"] for n in allnews] == ["new eth", "unclassified", "old btc"]
    assert allnews[1]["sentiment"] is None
    btc = (await env.c.get("/api/v1/ai/news?symbol=BTCUSDT")).json()
    assert [n["title"] for n in btc] == ["old btc"]


async def test_status_reports_worker_key_spend_and_budget(env: Env) -> None:  # noqa: F811
    s = (await env.c.get("/api/v1/ai/status")).json()
    assert s["worker_alive"] is False and s["key_configured"] is False  # no redis at all
    assert s["budget_usd"] == 20.0 and Decimal(str(s["month_spend_usd"])) == 0
    now = datetime.now(UTC)
    env.svc.redis = FakeRedis({"at": now.isoformat(), "enabled": True})
    assert env.svc.db
    async with env.svc.db.begin() as db:
        db.add(brief_row("BTCUSDT", 1))
    s = (await env.c.get("/api/v1/ai/status")).json()
    assert (
        s["worker_alive"]
        and s["key_configured"]
        and Decimal(str(s["month_spend_usd"])) == Decimal("0.01")
    )
    env.svc.redis = FakeRedis({"at": (now - timedelta(minutes=10)).isoformat(), "enabled": True})
    assert (await env.c.get("/api/v1/ai/status")).json()["worker_alive"] is False  # stale beat
    env.svc.redis = FakeRedis({"at": now.isoformat(), "enabled": False})
    j = (await env.c.get("/api/v1/ai/status")).json()
    assert j["worker_alive"] and not j["key_configured"]  # running, but headlines-only


async def test_refresh_is_validated_queued_and_rate_limited(env: Env) -> None:  # noqa: F811
    body = {"symbol": "BTCUSDT"}
    assert (await env.c.post("/api/v1/ai/briefs/refresh", json=body)).status_code == 503  # no redis
    r = FakeRedis()
    env.svc.redis = r
    assert (
        await env.c.post("/api/v1/ai/briefs/refresh", json={"symbol": "DOGEUSDT"})
    ).status_code == 422
    assert (await env.c.post("/api/v1/ai/briefs/refresh", json=body)).status_code == 202
    assert (
        await env.c.post("/api/v1/ai/briefs/refresh", json=body)
    ).status_code == 429  # costs money
    assert (
        await env.c.post("/api/v1/ai/briefs/refresh", json={"symbol": "ETHUSDT"})
    ).status_code == 202
    assert r.queue == ["BTCUSDT", "ETHUSDT"]


async def test_the_ai_endpoints_need_a_login(env: Env) -> None:  # noqa: F811
    import httpx

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(env.svc)), base_url="http://test"
    ) as anon:
        for path in ("/api/v1/ai/briefs", "/api/v1/ai/news", "/api/v1/ai/status"):
            assert (await anon.get(path)).status_code == 401
        assert (
            await anon.post("/api/v1/ai/briefs/refresh", json={"symbol": "BTCUSDT"})
        ).status_code == 401
