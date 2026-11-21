"""The one place that talks to Claude (SPEC 4.2).

Everything the AI layer does goes through ``LLMClient.complete``: structured output validated
by Pydantic, a hard timeout, and token counts for cost tracking. The AI layer may only produce
*scores and text*; it has no import path to the exchange or the order manager (see
``tests/test_ai_isolation.py``), so a model can never place an order.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Protocol, TypeVar

import anthropic
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMError(Exception):
    """The call failed, timed out or returned something that is not the requested schema."""


@dataclass(frozen=True, slots=True)
class LLMResult[T: BaseModel]:
    parsed: T
    tokens_in: int
    tokens_out: int
    cache_read: int
    latency_ms: int


class LLMClient(Protocol):
    async def complete[T2: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T2],
        max_tokens: int,
        effort: str = "low",
        timeout_s: float = 20.0,
    ) -> LLMResult[T2]: ...


class AnthropicLLM:
    """Claude via the official SDK. The API key never leaves this object."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=1)

    async def complete[T2: BaseModel](
        self,
        *,
        model: str,
        system: str,
        user: str,
        schema: type[T2],
        max_tokens: int,
        effort: str = "low",
        timeout_s: float = 20.0,
    ) -> LLMResult[T2]:
        t0 = time.monotonic()
        try:
            msg = await asyncio.wait_for(
                self._client.messages.parse(
                    model=model,
                    max_tokens=max_tokens,
                    # the system prompt is identical between calls: let the API cache it
                    system=[
                        {"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}
                    ],
                    messages=[{"role": "user", "content": user}],
                    output_format=schema,
                    output_config={"effort": effort},  # type: ignore[arg-type]
                ),
                timeout=timeout_s,
            )
        except TimeoutError as e:
            raise LLMError(f"timeout after {timeout_s:.0f}s") from e
        except anthropic.APIError as e:
            raise LLMError(f"{type(e).__name__}") from e  # never echo the message: may carry keys
        if msg.stop_reason == "refusal":
            raise LLMError("refusal")
        parsed = msg.parsed_output
        if parsed is None:
            raise LLMError(f"no valid {schema.__name__} in the response")
        u = msg.usage
        return LLMResult(
            parsed=parsed,
            tokens_in=u.input_tokens + (u.cache_creation_input_tokens or 0),
            tokens_out=u.output_tokens,
            cache_read=u.cache_read_input_tokens or 0,
            latency_ms=int((time.monotonic() - t0) * 1000),
        )
