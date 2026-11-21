"""Trade review after every closed trade, and a weekly summary (SPEC 4.2).

The journal explains *why* a trade won or lost so patterns can be spotted. It is commentary only:
it never changes a bot, a size or a limit. Inputs are our own records (signal reasons, R, exit
reason), not internet text.
"""

from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import String, cast, func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.service import AiService
from app.core.models import AiAnalysis, AnalysisKind, Bot, Position, Signal, Trade

PER_CYCLE = 3  # reviews per worker cycle: a burst of closes must not become a burst of cost

SYSTEM_TRADE = """You review one closed spot trade of an automated strategy for its journal.
Judge the process, not just the outcome: was the setup valid per the stated reasons, was the stop
sensible, and did the exit match the plan? Be honest that one trade is a small sample.
Return: verdict (win_clean, win_lucky, loss_valid, loss_error or scratch), why_th (2-3 Thai
sentences), lessons_th (up to 3 short Thai points; empty if nothing is worth noting)."""

SYSTEM_WEEK = """You write the weekly journal summary of an automated trading system from the
statistics given. Look for repeated patterns (a strategy, a coin, an exit reason), not for stories.
State clearly when the sample is too small to conclude. Return: summary_th (3 Thai sentences),
patterns_th (up to 3), suggestions_th (up to 3 things worth investigating; never orders)."""


class TradeReview(BaseModel):
    verdict: Literal["win_clean", "win_lucky", "loss_valid", "loss_error", "scratch"]
    why_th: str
    lessons_th: list[str]


class WeeklyReview(BaseModel):
    summary_th: str
    patterns_th: list[str]
    suggestions_th: list[str]


def week_start(d: datetime) -> datetime:
    d = d.astimezone(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
    return d - timedelta(days=d.weekday())


async def unreviewed_trades(
    sessions: async_sessionmaker[AsyncSession], limit: int = PER_CYCLE
) -> list[tuple[Trade, Position, Bot | None, Signal | None]]:
    async with sessions() as db:
        done = select(AiAnalysis.input["trade_id"].astext).where(
            AiAnalysis.kind == AnalysisKind.REVIEW,
            AiAnalysis.input["trade_id"].is_not(None),
            AiAnalysis.cost_usd > 0,  # a failed attempt (nothing billed) is retried, not "done"
        )
        rows = (
            await db.execute(
                select(Trade, Position, Bot)
                .join(Position, Position.id == Trade.position_id)
                .outerjoin(Bot, Bot.id == Position.bot_id)
                .where(cast(Trade.id, String).not_in(done))
                .order_by(Trade.created_at)
                .limit(limit)
            )
        ).all()
        out: list[tuple[Trade, Position, Bot | None, Signal | None]] = []
        for t, p, b in rows:
            sid = (p.state or {}).get("signal_id")
            sig = await db.get(Signal, sid) if sid else None
            out.append((t, p, b, sig))
    return out


async def review_pending(
    ai: AiService, sessions: async_sessionmaker[AsyncSession], model: str
) -> int:
    n = 0
    for t, p, b, sig in await unreviewed_trades(sessions):
        facts: dict[str, Any] = {
            "symbol": p.symbol,
            "side": str(p.side),
            "bot": b.name if b else "manual",
            "strategy": sig.strategy if sig else "manual",
            "entry": float(p.avg_entry),
            "stop": None if p.stop is None else float(p.stop),
            "pnl_r": float(t.pnl_r),
            "exit_reason": t.exit_reason,
            "holding_minutes": t.holding_minutes,
            "score": None if sig is None or sig.score is None else float(sig.score),
            "reasons": sig.reasons if sig else None,
            "exit_plan": sig.exit_plan if sig else None,
        }
        out = await ai.run(
            kind=AnalysisKind.REVIEW,
            symbol=p.symbol,
            model=model,
            system=SYSTEM_TRADE,
            user=str(facts),
            schema=TradeReview,
            input_payload={"trade_id": str(t.id), **facts},
            max_tokens=700,
        )
        if out is None:
            break  # outage or budget: stop this cycle, try again next time
        n += 1
    return n


async def weekly_due(sessions: async_sessionmaker[AsyncSession], now: datetime) -> datetime | None:
    """Start of the previous ISO week if it had trades and has no summary yet."""
    start = week_start(now) - timedelta(days=7)
    end = start + timedelta(days=7)
    async with sessions() as db:
        n = (
            await db.execute(
                select(func.count())
                .select_from(Trade)
                .where(Trade.created_at >= start, Trade.created_at < end)
            )
        ).scalar_one()
        have = (
            await db.execute(
                select(AiAnalysis.id)
                .where(
                    AiAnalysis.kind == AnalysisKind.REVIEW,
                    AiAnalysis.input["week"].astext == start.date().isoformat(),
                    AiAnalysis.cost_usd > 0,
                )
                .limit(1)
            )
        ).first()
    return start if n and have is None else None


async def weekly_summary(
    ai: AiService, sessions: async_sessionmaker[AsyncSession], model: str, start: datetime
) -> WeeklyReview | None:
    end = start + timedelta(days=7)
    async with sessions() as db:
        rows = (
            await db.execute(
                select(Trade, Position)
                .join(Position, Position.id == Trade.position_id)
                .where(Trade.created_at >= start, Trade.created_at < end)
            )
        ).all()
    by: dict[str, dict[str, dict[str, float]]] = {"symbol": {}, "exit_reason": {}}
    for t, p in rows:
        for dim, key in (("symbol", p.symbol), ("exit_reason", t.exit_reason)):
            c = by[dim].setdefault(key, {"n": 0, "total_r": 0.0})
            c["n"] += 1
            c["total_r"] = round(c["total_r"] + float(t.pnl_r), 3)
    wins = sum(1 for t, _ in rows if t.pnl_r > 0)
    stats = {
        "week": start.date().isoformat(),
        "n_trades": len(rows),
        "win_rate": round(wins / len(rows), 3) if rows else None,
        "total_r": round(sum(float(t.pnl_r) for t, _ in rows), 3),
        **by,
    }
    return await ai.run(
        kind=AnalysisKind.REVIEW,
        symbol=None,
        model=model,
        system=SYSTEM_WEEK,
        user=str(stats),
        schema=WeeklyReview,
        input_payload=stats,
        max_tokens=900,
    )
