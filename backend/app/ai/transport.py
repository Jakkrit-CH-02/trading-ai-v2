"""Chat transport between the API and the ai-worker (Redis).

The API holds no Anthropic key, so it cannot talk to Claude itself: it queues the request, the
worker streams events into a per-request Redis stream, and the API relays them as SSE. Both sides
validate the messages, so neither trusts the other (or the browser) for limits.
"""

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai.chat import ChatBackend, run_chat
from app.ai.service import AiService

CHAT_REQ = "ai:chat:req"
MAX_MESSAGES = 20
MAX_CHARS = 4000
RESP_TTL_S = 300
READ_TIMEOUT_S = 90.0
RATE_PER_HOUR = 30


def resp_key(rid: str) -> str:
    return f"ai:chat:resp:{rid}"


def clean_messages(raw: Any) -> list[dict[str, str]] | None:
    """Plain user/assistant text only, bounded, ending with a user message; else None."""
    if not isinstance(raw, list) or not raw or len(raw) > MAX_MESSAGES:
        return None
    out: list[dict[str, str]] = []
    for m in raw:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            return None
        c = m.get("content")
        if not isinstance(c, str) or not c.strip() or len(c) > MAX_CHARS:
            return None
        out.append({"role": str(m["role"]), "content": c})
    return out if out[-1]["role"] == "user" and out[0]["role"] == "user" else None


async def serve_request(
    redis: Any,
    backend: ChatBackend,
    ai: AiService,
    sessions: async_sessionmaker[AsyncSession],
    model: str,
    payload: str,
) -> None:
    """Worker side: answer one queued request by appending events to its response stream."""
    try:
        req = json.loads(payload)
        rid, history = str(req["id"]), clean_messages(req["messages"])
    except (ValueError, KeyError, TypeError):
        return  # not something we queued: drop it
    if not rid.isalnum() or len(rid) > 64:
        return
    key = resp_key(rid)

    async def emit(ev: dict[str, Any]) -> None:
        await redis.xadd(key, {"e": json.dumps(ev, ensure_ascii=False)}, maxlen=500)
        await redis.expire(key, RESP_TTL_S)

    if history is None:
        await emit({"type": "error", "message": "ข้อความไม่ถูกต้อง"})
        return
    await run_chat(backend, ai, sessions, model, history, emit)


async def read_events(
    redis: Any, rid: str, timeout_s: float = READ_TIMEOUT_S
) -> AsyncIterator[dict[str, Any]]:
    """API side: relay events until done/error or the timeout (then a final error event)."""
    key, last = resp_key(rid), "0"
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        resp = await redis.xread({key: last}, block=1000, count=50)
        for _, entries in resp or []:
            for entry_id, fields in entries:
                last = entry_id
                ev = json.loads(fields["e"])
                yield ev
                if ev.get("type") in ("done", "error"):
                    return
    yield {"type": "error", "message": "AI ไม่ตอบสนอง ลองใหม่อีกครั้ง"}
