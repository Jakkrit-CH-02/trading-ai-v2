"""Claude streaming backend for the chat (the key stays inside this object)."""

from collections.abc import Awaitable, Callable
from typing import Any

import anthropic

from app.ai.chat import ToolUse, TurnResult
from app.ai.llm import LLMError


class AnthropicChat:
    def __init__(self, api_key: str) -> None:
        self._client = anthropic.AsyncAnthropic(api_key=api_key, max_retries=1)

    async def turn(
        self,
        *,
        model: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        max_tokens: int,
        on_text: Callable[[str], Awaitable[None]],
    ) -> TurnResult:
        try:
            async with self._client.messages.stream(
                model=model,
                max_tokens=max_tokens,
                system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=messages,  # type: ignore[arg-type]
                tools=tools,  # type: ignore[arg-type]
                output_config={"effort": "low"},
            ) as stream:
                async for t in stream.text_stream:
                    await on_text(t)
                final = await stream.get_final_message()
        except anthropic.APIError as e:
            raise LLMError(type(e).__name__) from e  # never echo the message: may carry keys
        if final.stop_reason == "refusal":
            raise LLMError("refusal")
        u = final.usage
        return TurnResult(
            content=list(final.content),
            tool_uses=[
                ToolUse(b.id, b.name, dict(b.input))
                for b in final.content
                if b.type == "tool_use" and isinstance(b.input, dict)
            ],
            tokens_in=u.input_tokens + (u.cache_creation_input_tokens or 0),
            tokens_out=u.output_tokens,
            cache_read=u.cache_read_input_tokens or 0,
        )
