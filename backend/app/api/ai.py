"""AI Analyst endpoints (SPEC 8.1): briefs, headlines, status, refresh.

The API never calls an LLM and holds no Anthropic key. ``refresh`` only asks the ai-worker (via a
Redis list) to run early; the worker owns the key, the budget and the prompts.
"""

import json
from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select

from app.ai.service import month_start
from app.api.services import Services, get_services
from app.auth.deps import Db, current_user
from app.core.models import AiAnalysis, AnalysisKind, NewsItem

router = APIRouter(prefix="/api/v1/ai", dependencies=[Depends(current_user)], tags=["ai"])
Svc = Annotated[Services, Depends(get_services)]
HEARTBEAT_KEY = "ai:heartbeat"
REFRESH_LIST = "ai:refresh"
REFRESH_COOLDOWN_S = 600


class BriefOut(BaseModel):
    id: str
    symbol: str
    created_at: datetime
    model: str
    bias: Literal["bull", "neutral", "bear"]
    s_ai: float
    support: list[float]
    resistance: list[float]
    risks: list[str]
    summary_th: list[str]
    cost_usd: Decimal


class NewsOut(BaseModel):
    id: str
    source: str
    title: str
    url: str
    published_at: datetime
    symbols: list[str]
    sentiment: float | None
    severity: float | None
    category: str | None


class AiStatus(BaseModel):
    worker_alive: bool
    key_configured: bool
    month_spend_usd: Decimal
    budget_usd: float
    last_news_at: datetime | None


class RefreshIn(BaseModel):
    symbol: str


def to_brief(a: AiAnalysis) -> BriefOut | None:
    o: dict[str, Any] = a.output
    if "error" in o or a.symbol is None:
        return None  # a failed call is kept for audit but is not a brief
    try:
        return BriefOut(
            id=str(a.id), symbol=a.symbol, created_at=a.created_at, model=a.model,
            bias=o["bias"], s_ai=o["s_ai"], support=o["support"], resistance=o["resistance"],
            risks=o["risks"], summary_th=o["summary_th"], cost_usd=a.cost_usd,
        )  # fmt: skip
    except (KeyError, ValueError):
        return None


@router.get("/briefs", response_model=list[BriefOut])
async def briefs(
    db: Db, symbol: str | None = None, limit: int = Query(10, ge=1, le=50)
) -> list[BriefOut]:
    """Newest brief per coin, or the history of one coin when ``symbol`` is given."""
    q = select(AiAnalysis).where(AiAnalysis.kind == AnalysisKind.BRIEF)
    if symbol:
        q = q.where(AiAnalysis.symbol == symbol)
    rows = (await db.execute(q.order_by(AiAnalysis.created_at.desc()).limit(200))).scalars()
    out: list[BriefOut] = []
    seen: set[str] = set()
    for a in rows:
        b = to_brief(a)
        if b is None or (not symbol and b.symbol in seen):
            continue
        seen.add(b.symbol)
        out.append(b)
    return out[:limit]


@router.get("/news", response_model=list[NewsOut])
async def news(
    db: Db, symbol: str | None = None, limit: int = Query(30, ge=1, le=100)
) -> list[NewsOut]:
    q = select(NewsItem).order_by(NewsItem.published_at.desc()).limit(limit)
    if symbol:
        q = q.where(NewsItem.symbols.contains([symbol.removesuffix("USDT")]))
    return [
        NewsOut(
            id=str(n.id), source=n.source, title=n.title, url=n.url, published_at=n.published_at,
            symbols=list(n.symbols), sentiment=None if n.sentiment is None else float(n.sentiment),
            severity=None if n.severity is None else float(n.severity), category=n.category,
        )
        for n in (await db.execute(q)).scalars()
    ]  # fmt: skip


@router.get("/status", response_model=AiStatus)
async def status(db: Db, svc: Svc) -> AiStatus:
    alive, configured = False, False
    if svc.redis is not None:
        try:
            raw = await svc.redis.get(HEARTBEAT_KEY)
            if raw:
                beat = json.loads(raw)
                age = (datetime.now(UTC) - datetime.fromisoformat(beat["at"])).total_seconds()
                alive, configured = age <= 90, bool(beat.get("enabled"))
        except Exception:  # an unreadable heartbeat means "not alive", never an error page
            alive = configured = False
    spend = (
        await db.execute(
            select(func.coalesce(func.sum(AiAnalysis.cost_usd), 0)).where(
                AiAnalysis.created_at >= month_start(datetime.now(UTC))
            )
        )
    ).scalar_one()
    last = (await db.execute(select(func.max(NewsItem.published_at)))).scalar_one()
    return AiStatus(
        worker_alive=alive,
        key_configured=configured,
        month_spend_usd=Decimal(spend),
        budget_usd=svc.settings.ai_monthly_budget_usd,
        last_news_at=last,
    )


@router.post("/briefs/refresh", status_code=202)
async def refresh(body: RefreshIn, svc: Svc) -> dict[str, str]:
    if body.symbol not in svc.settings.symbols:
        raise HTTPException(422, f"unsupported symbol: {body.symbol}")
    if svc.redis is None:
        raise HTTPException(503, "the AI worker is not reachable")
    # one request per coin per 10 minutes: every refresh costs real money
    fresh = await svc.redis.set(f"ai:refresh:{body.symbol}", "1", ex=REFRESH_COOLDOWN_S, nx=True)
    if not fresh:
        raise HTTPException(429, "this coin was refreshed a moment ago; try again in a few minutes")
    await svc.redis.rpush(REFRESH_LIST, body.symbol)
    return {"status": "queued"}
