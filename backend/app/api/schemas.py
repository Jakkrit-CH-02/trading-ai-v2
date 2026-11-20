"""Response models for /api/v1. Money and quantities are ``Decimal`` (serialised as strings);
chart series are analytics and use floats."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field


class CandleOut(BaseModel):
    time: int = Field(description="Open time, UTC epoch seconds")
    open: float
    high: float
    low: float
    close: float
    volume: float


class Ticker(BaseModel):
    symbol: str
    last: Decimal
    change24h_pct: Decimal
    high: Decimal
    low: Decimal
    volume: Decimal


class MarketStats(Ticker):
    funding_rate: Decimal | None = Field(None, description="Spot has no funding; null")
    tick_size: Decimal | None = None


class WatchItem(BaseModel):
    symbol: str
    name: str
    last: Decimal
    change24h_pct: Decimal
    spark: list[float]
    tick_size: Decimal | None = None


class Allocation(BaseModel):
    label: str
    pct: int


class DashboardSummary(BaseModel):
    connected: bool = Field(description="False when no trading account is configured")
    mode: Literal["paper", "live"] = "paper"
    equity: Decimal = Decimal(0)
    pnl_today: Decimal | None = Field(None, description="vs. first equity seen this UTC day")
    pnl_today_pct: Decimal | None = None
    available: Decimal = Decimal(0)
    in_orders: Decimal = Decimal(0)
    allocation: list[Allocation] = []


class OrderOut(BaseModel):
    id: str
    symbol: str
    side: Literal["BUY", "SELL"]
    type: str
    status: str
    price: Decimal | None
    qty: Decimal
    executed_qty: Decimal
    ts: datetime | None
    source: str | None = None


class Sentiment(BaseModel):
    value: int
    label: str
    updated: datetime | None = None


class BotOut(BaseModel):
    id: str
    name: str
    strategy: str
    status: Literal["RUNNING", "PAUSED", "KILLED"]
    pnl_today: Decimal = Decimal(0)


class BotsSummary(BaseModel):
    bots: list[BotOut]
    running: int
    open_risk_pct: Decimal
    open_risk_cap_pct: Decimal


class BreakerOut(BaseModel):
    kind: str
    detail: str
    until: datetime | None = None


class RiskStatus(BaseModel):
    kill_switch: bool
    entries_blocked: bool
    breakers: list[BreakerOut]
    open_risk_cap_pct: Decimal
