from datetime import datetime
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class StrategyPreset(BaseModel):
    id: str
    name: str
    description: str
    params: dict[str, float]
    warning: str | None = None


class BotCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    account_id: UUID
    symbols: list[str] = Field(min_length=1, max_length=10)
    strategy: Literal["s1", "s2", "s3", "s4"]
    params: dict[str, float] = {}


class BotPatch(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=64)
    symbols: list[str] | None = Field(None, min_length=1, max_length=10)
    params: dict[str, float] | None = None


class ConfigOut(BaseModel):
    strategy: str
    params: dict[str, Any]
    version: int


class BotDetail(BaseModel):
    id: UUID
    name: str
    account_id: UUID
    market: str
    symbols: list[str]
    status: str
    mode: str
    config: ConfigOut | None
    created_at: datetime


class GateCheckOut(BaseModel):
    name: str
    ok: bool
    detail: str


class GatesOut(BaseModel):
    allowed: bool
    checks: list[GateCheckOut]


class PerformanceOut(BaseModel):
    n_trades: int
    win_rate: float
    profit_factor: float | None
    expectancy_r: float
    net_pnl: Decimal
    max_drawdown: float
    sharpe: float
    equity: list[tuple[int, float]] = Field(description="[epoch seconds, cumulative net PnL]")
    drawdown: list[tuple[int, float]]


class SignalOut(BaseModel):
    id: UUID
    ts: datetime
    symbol: str
    strategy: str
    side: str
    entry: Decimal
    stop: Decimal
    tp1: Decimal | None
    s_tech: Decimal | None
    s_ml: Decimal | None
    s_ai: Decimal | None
    score: Decimal | None
    decision: str
    reject_reason: str | None
    rr: float | None = Field(None, description="(tp1 - entry) / (entry - stop) before costs")
    checks: list[GateCheckOut] = Field(
        description="pre-trade checklist as far as it can be derived"
    )


class TradeOut(BaseModel):
    id: UUID
    symbol: str
    opened_at: datetime
    closed_at: datetime | None
    pnl_usdt: Decimal
    pnl_r: Decimal
    fees: Decimal
    exit_reason: str


class GoLiveIn(BaseModel):
    confirm: Literal[True]


class RiskProfileOut(BaseModel):
    risk_per_trade: Decimal
    max_positions: int
    max_symbol_exposure: Decimal
    max_total_exposure: Decimal
    max_open_risk: Decimal
    max_bucket_risk: Decimal
    min_cash_reserve: Decimal
    daily_loss: Decimal
    weekly_loss: Decimal
    max_drawdown: Decimal


class RiskEventOut(BaseModel):
    id: UUID
    ts: datetime
    type: str
    severity: str
    payload: dict[str, Any]
    resolved_at: datetime | None


class KillIn(BaseModel):
    reason: str = Field("manual", max_length=200)


class AccountIn(BaseModel):
    label: str = Field(min_length=1, max_length=64)
    api_key: str = Field(min_length=8, max_length=256)
    api_secret: str = Field(min_length=8, max_length=512)
    key_type: Literal["HMAC", "Ed25519"] = "HMAC"
    is_testnet: bool = True


class AccountOut(BaseModel):
    id: UUID
    label: str
    exchange: str
    key_type: str
    is_testnet: bool
    api_key_last4: str
    permissions_checked_at: datetime | None


class LogEntryOut(BaseModel):
    """One line of a bot's activity feed, merged from signals, orders, trades, risk events and
    the audit trail."""

    ts: datetime
    kind: Literal["signal", "order", "trade", "risk", "audit"]
    level: Literal["info", "warning", "critical"]
    title: str
    detail: str = ""


class RunnerStatus(BaseModel):
    alive: bool
    last_beat: datetime | None = None
    age_s: float | None = None
