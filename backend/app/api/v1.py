"""Read-only REST endpoints under /api/v1 that feed the dashboard (SPEC 8.1)."""

import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Literal

import httpx
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.schemas import (
    Allocation,
    BotsSummary,
    BreakerOut,
    CandleOut,
    DashboardSummary,
    MarketStats,
    OrderOut,
    RiskStatus,
    Sentiment,
    Ticker,
    WatchItem,
)
from app.api.services import NAMES, Services, get_services
from app.auth.deps import current_user
from app.exchange.errors import ExchangeError
from app.exchange.types import INTERVAL_MS

router = APIRouter(prefix="/api/v1", dependencies=[Depends(current_user)])
Svc = Annotated[Services, Depends(get_services)]
Interval = Literal["15m", "1h", "4h", "1d"]


def _check_symbol(s: Services, symbol: str) -> str:
    symbol = symbol.upper()
    if symbol not in s.settings.symbols:
        raise HTTPException(404, f"unknown symbol {symbol}")
    return symbol


async def load_candles(s: Services, symbol: str, interval: str, limit: int) -> list[CandleOut]:
    """Closed candles, newest ``limit``. ``1d`` is aggregated from stored 1h candles (UTC days)."""
    end = datetime.now(UTC)
    src = "1h" if interval == "1d" else interval
    span = (limit + 1) * (24 if interval == "1d" else 1) * INTERVAL_MS[src]  # +1: partial bucket
    ks = await s.candles.load(symbol, src, end - timedelta(milliseconds=span), end)
    if interval == "1d" and ks:
        df = pd.DataFrame(
            {
                "t": [k.open_time for k in ks],
                "o": [float(k.o) for k in ks],
                "h": [float(k.h) for k in ks],
                "l": [float(k.l) for k in ks],
                "c": [float(k.c) for k in ks],
                "v": [float(k.v) for k in ks],
            }
        ).set_index("t")
        d = (
            df.resample("1D")
            .agg({"o": "first", "h": "max", "l": "min", "c": "last", "v": "sum"})
            .dropna()
        )
        return [
            CandleOut(
                time=int(pd.Timestamp(str(t)).timestamp()),
                open=r.o,
                high=r.h,
                low=r.l,
                close=r.c,
                volume=r.v,
            )
            for t, r in d.tail(limit).iterrows()
        ]
    return [
        CandleOut(
            time=int(k.open_time.timestamp()),
            open=float(k.o),
            high=float(k.h),
            low=float(k.l),
            close=float(k.c),
            volume=float(k.v),
        )
        for k in ks[-limit:]
    ]


async def _tickers(s: Services, symbols: list[str]) -> dict[str, Ticker]:
    try:
        return await s.market.tickers(symbols)
    except (httpx.HTTPError, KeyError, ValueError) as e:
        raise HTTPException(502, "market data unavailable") from e


@router.get("/markets/{symbol}/candles", response_model=list[CandleOut])
async def candles(
    s: Svc,
    symbol: str,
    interval: Interval = "1h",
    limit: Annotated[int, Query(ge=1, le=1000)] = 200,
) -> list[CandleOut]:
    return await load_candles(s, _check_symbol(s, symbol), interval, limit)


@router.get("/markets/{symbol}/stats", response_model=MarketStats)
async def stats(s: Svc, symbol: str) -> MarketStats:
    symbol = _check_symbol(s, symbol)
    t = (await _tickers(s, [symbol])).get(symbol)
    if t is None:
        raise HTTPException(502, "market data unavailable")
    return MarketStats(**t.model_dump(), funding_rate=None)


@router.get("/watchlist", response_model=list[WatchItem])
async def watchlist(s: Svc) -> list[WatchItem]:
    symbols = s.settings.symbols
    ticks = await _tickers(s, symbols)
    sparks = await asyncio.gather(*(load_candles(s, sym, "1h", 24) for sym in symbols))
    return [
        WatchItem(
            symbol=sym,
            name=NAMES.get(sym, sym.removesuffix("USDT")),
            last=ticks[sym].last,
            change24h_pct=ticks[sym].change24h_pct,
            spark=[c.close for c in sp],
        )
        for sym, sp in zip(symbols, sparks, strict=True)
        if sym in ticks
    ]


def _q(d: Decimal) -> Decimal:
    """8 dp (Binance precision) so values never serialise as 0E-16."""
    return d.quantize(Decimal("0.00000001"))


async def build_summary(s: Services) -> DashboardSummary:
    if s.trading is None:
        return DashboardSummary(connected=False)
    try:
        balances = await s.trading.balances()
    except ExchangeError as e:
        raise HTTPException(502, "exchange unavailable") from e
    assets = [a for a, b in balances.items() if b.total > 0 and a != "USDT"]
    prices = (
        await _tickers(s, [f"{a}USDT" for a in assets if f"{a}USDT" in s.settings.symbols])
        if assets
        else {}
    )
    values: dict[str, Decimal] = {}
    for a, b in balances.items():
        if b.total <= 0:
            continue
        if a == "USDT":
            values[a] = b.total
        elif (t := prices.get(f"{a}USDT")) is not None:
            values[a] = b.total * t.last
    equity = sum(values.values(), Decimal(0))
    usdt = balances.get("USDT")
    locked_value = (usdt.locked if usdt else Decimal(0)) + sum(
        (balances[a].locked * prices[f"{a}USDT"].last for a in assets if f"{a}USDT" in prices),
        Decimal(0),
    )
    pnl, pct = s.day_start.pnl(equity, datetime.now(UTC)) if equity > 0 else (None, None)
    alloc: list[Allocation] = []
    if equity > 0:
        held = ((a, v) for a, v in values.items() if a != "USDT" and round(v / equity * 100) >= 1)
        ranked = sorted(held, key=lambda x: -x[1])[:3]  # dust (<1%) is folded into Cash
        shown = sum((v for _, v in ranked), Decimal(0))
        alloc = [Allocation(label=a, pct=round(v / equity * 100)) for a, v in ranked]
        alloc.append(Allocation(label="Cash", pct=max(0, 100 - round(shown / equity * 100))))
    return DashboardSummary(
        connected=True,
        equity=_q(equity),
        pnl_today=None if pnl is None else _q(pnl),
        pnl_today_pct=None if pct is None else _q(pct),
        available=usdt.free if usdt else Decimal(0),
        in_orders=_q(locked_value),
        allocation=alloc,
    )


@router.get("/dashboard/summary", response_model=DashboardSummary)
async def summary(s: Svc) -> DashboardSummary:
    return await build_summary(s)


@router.get("/orders", response_model=list[OrderOut])
async def orders(s: Svc, status: Literal["all", "open", "filled"] = "all") -> list[OrderOut]:
    """Open orders come from the exchange. Filled/cancelled history needs the execution store
    (not built yet), so those filters return only what the exchange still reports as open."""
    if s.trading is None or status == "filled":
        return []
    try:
        infos = await s.trading.open_orders()
    except ExchangeError as e:
        raise HTTPException(502, "exchange unavailable") from e
    return [
        OrderOut(
            id=o.client_order_id,
            symbol=o.symbol,
            side="BUY" if str(o.side).upper().endswith("BUY") else "SELL",
            type=str(o.type),
            status=str(o.status),
            price=o.price,
            qty=o.qty,
            executed_qty=o.executed_qty,
            ts=o.ts,
        )
        for o in infos
    ]


@router.get("/sentiment", response_model=Sentiment)
async def sentiment(s: Svc) -> Sentiment:
    v = await s.market.fear_greed()
    if v is None:
        raise HTTPException(502, "sentiment unavailable")
    return v


@router.get("/bots", response_model=BotsSummary)
async def bots(s: Svc) -> BotsSummary:
    """No bot runtime yet (Phase 5): an honest empty list rather than invented bots."""
    return BotsSummary(
        bots=[],
        running=0,
        open_risk_pct=Decimal(0),
        open_risk_cap_pct=s.profile.max_open_risk * 100,
    )


@router.get("/risk/status", response_model=RiskStatus)
async def risk_status(s: Svc) -> RiskStatus:
    b = s.breakers  # None until a trading engine attaches; then nothing can be blocked either
    now = datetime.now(UTC)
    active = b.active(now) if b else []
    return RiskStatus(
        kill_switch=bool(b and b.kill_switch_active),
        entries_blocked=bool(b and b.entries_blocked(now)),
        breakers=[BreakerOut(kind=str(x.kind), detail=x.detail, until=x.until) for x in active],
        open_risk_cap_pct=s.profile.max_open_risk * 100,
    )
