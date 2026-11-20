"""``/ws`` — one connection per tab, multiplexed channels (SPEC 8.2).

Client: ``{"op":"subscribe","channels":["ticker:BTCUSDT","portfolio","risk"]}``.
Server: ``{"ch": str, "ts": epoch_ms, "data": {...}}``. Implemented: ticker:{symbol} (1/s),
portfolio (every 5 s) and risk (on subscribe + whenever it changes)."""

import asyncio
import contextlib
import json
import time
from typing import Any

import httpx
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.api.services import Services
from app.api.v1 import build_summary, risk_status

router = APIRouter()


def _msg(ch: str, data: Any) -> str:
    return json.dumps({"ch": ch, "ts": int(time.time() * 1000), "data": data})


async def _pump(ws: WebSocket, s: Services, subs: set[str]) -> None:
    tick = 0
    last_risk: str | None = None
    while True:
        symbols = [c.split(":", 1)[1].upper() for c in subs if c.startswith("ticker:")]
        symbols = [x for x in symbols if x in s.settings.symbols]
        if symbols:
            try:
                for sym, t in (await s.market.tickers(symbols)).items():
                    await ws.send_text(_msg(f"ticker:{sym}", json.loads(t.model_dump_json())))
            except (httpx.HTTPError, KeyError, ValueError):
                pass  # transient; the next second retries and the client keeps its last value
        if "portfolio" in subs and tick % 5 == 0:
            with contextlib.suppress(Exception):
                await ws.send_text(
                    _msg("portfolio", json.loads((await build_summary(s)).model_dump_json()))
                )
        if "risk" in subs:
            payload = (await risk_status(s)).model_dump_json()
            if payload != last_risk:
                last_risk = payload
                await ws.send_text(_msg("risk", json.loads(payload)))
        else:
            last_risk = None
        tick += 1
        await asyncio.sleep(1)


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    s: Services = ws.app.state.services
    await ws.accept()
    subs: set[str] = set()
    pump = asyncio.create_task(_pump(ws, s, subs))
    try:
        while True:
            try:
                msg = json.loads(await ws.receive_text())
            except json.JSONDecodeError:
                await ws.send_text(
                    json.dumps(
                        {
                            "ch": "error",
                            "ts": int(time.time() * 1000),
                            "data": {"error": "bad json"},
                        }
                    )
                )
                continue
            channels = [c for c in msg.get("channels", []) if isinstance(c, str)]
            if msg.get("op") == "subscribe":
                subs.update(channels)
            elif msg.get("op") == "unsubscribe":
                subs.difference_update(channels)
    except WebSocketDisconnect:
        pass
    finally:
        pump.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await pump
