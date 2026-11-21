"""Run one LLM task: budget guard, timeout, validation and an ``ai_analyses`` row (SPEC 4.2).

``AiService.run`` never raises for an LLM problem. It returns ``None`` and the caller carries on
with the neutral default (S_ai = 50), so an outage, a refusal, a schema violation or an exhausted
budget can slow the AI down but never the bot.
"""

import hashlib
import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.llm import LLMClient, LLMError
from app.ai.pricing import cost_usd
from app.core.models import AiAnalysis, AnalysisKind
from app.notify.telegram import Notifier, NullNotifier

log = structlog.get_logger()
NEUTRAL = 50.0  # S_ai when the LLM has nothing (valid) to say


def month_start(now: datetime) -> datetime:
    return now.astimezone(UTC).replace(day=1, hour=0, minute=0, second=0, microsecond=0)


class AiService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        llm: LLMClient,
        *,
        budget_usd: float,
        timeout_s: float = 20.0,
        notifier: Notifier | None = None,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.sessions = sessions
        self.llm = llm
        self.budget = Decimal(str(budget_usd))
        self.timeout_s = timeout_s
        self.notifier = notifier or NullNotifier()
        self.now = now
        self._warned_month: datetime | None = None

    async def month_spend(self) -> Decimal:
        async with self.sessions() as db:
            q = select(func.coalesce(func.sum(AiAnalysis.cost_usd), 0)).where(
                AiAnalysis.created_at >= month_start(self.now())
            )
            return Decimal((await db.execute(q)).scalar_one())

    async def _budget_ok(self) -> bool:
        spent = await self.month_spend()
        month = month_start(self.now())
        if spent >= self.budget * Decimal("0.8") and self._warned_month != month:
            self._warned_month = month
            await self.notifier.send(f"AI spend ${spent:.2f} of ${self.budget:.2f} this month")
        return spent < self.budget

    async def run[T: BaseModel](
        self,
        *,
        kind: AnalysisKind,
        symbol: str | None,
        model: str,
        system: str,
        user: str,
        schema: type[T],
        input_payload: dict[str, Any],
        max_tokens: int = 1500,
        effort: str = "low",
    ) -> T | None:
        if not await self._budget_ok():
            log.warning("ai.budget_exhausted", kind=kind.value)
            return None
        prompt_hash = hashlib.sha256((system + "\n" + user).encode()).hexdigest()
        try:
            res = await self.llm.complete(
                model=model,
                system=system,
                user=user,
                schema=schema,
                max_tokens=max_tokens,
                effort=effort,
                timeout_s=self.timeout_s,
            )
        except (LLMError, ValidationError) as e:
            log.warning("ai.call_failed", kind=kind.value, error=str(e)[:120])
            await self._record(
                kind, symbol, model, prompt_hash, input_payload, {"error": str(e)[:200]}
            )
            return None
        out = json.loads(res.parsed.model_dump_json())
        await self._record(
            kind,
            symbol,
            model,
            prompt_hash,
            input_payload,
            out,
            tokens_in=res.tokens_in,
            tokens_out=res.tokens_out,
            cost=cost_usd(model, res.tokens_in, res.tokens_out, res.cache_read),
            latency_ms=res.latency_ms,
        )
        return res.parsed

    async def _record(
        self,
        kind: AnalysisKind,
        symbol: str | None,
        model: str,
        prompt_hash: str,
        input_payload: dict[str, Any],
        output: dict[str, Any],
        *,
        tokens_in: int = 0,
        tokens_out: int = 0,
        cost: Decimal = Decimal(0),
        latency_ms: int = 0,
    ) -> None:
        async with self.sessions.begin() as db:
            db.add(
                AiAnalysis(
                    symbol=symbol,
                    kind=kind,
                    model=model,
                    prompt_hash=prompt_hash,
                    input=input_payload,
                    output=output,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_usd=cost,
                    latency_ms=latency_ms,
                )
            )
