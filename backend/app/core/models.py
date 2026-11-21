"""ORM models for every table in SPEC section 7.

Money/price/qty columns are ``NUMERIC(28,10)`` (never float). All timestamps are
``TIMESTAMPTZ`` stored as UTC. Every table has ``created_at`` / ``updated_at``.
"""

import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


def _num() -> Numeric[Decimal]:
    return Numeric(28, 10)


def _enum(cls: type[enum.Enum]) -> Enum:
    return Enum(
        cls,
        native_enum=False,
        length=16,
        values_callable=lambda e: [m.value for m in e],
        validate_strings=True,
    )


class Market(enum.StrEnum):
    SPOT = "SPOT"
    USDM = "USDM"


class BotStatus(enum.StrEnum):
    DRAFT = "DRAFT"
    PAPER = "PAPER"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    KILLED = "KILLED"


class BotMode(enum.StrEnum):
    BACKTEST = "backtest"
    PAPER = "paper"
    LIVE = "live"


class Side(enum.StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class Decision(enum.StrEnum):
    TAKEN = "TAKEN"
    SKIPPED = "SKIPPED"
    REJECTED = "REJECTED"


class OrderLeg(enum.StrEnum):
    ENTRY = "ENTRY"
    SL = "SL"
    TP = "TP"
    EXIT = "EXIT"


class PositionStatus(enum.StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class AnalysisKind(enum.StrEnum):
    NEWS = "news"
    BRIEF = "brief"
    REVIEW = "review"
    CHAT = "chat"


class Timestamps:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


def _pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()")
    )


def _ts(nullable: bool = True) -> Mapped[datetime | None]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class User(Timestamps, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = _pk()
    email: Mapped[str] = mapped_column(String(320), unique=True)
    password_hash: Mapped[str] = mapped_column(Text)  # argon2id
    totp_secret_enc: Mapped[bytes | None] = mapped_column(LargeBinary)
    role: Mapped[str] = mapped_column(String(16), server_default="admin")


class ExchangeAccount(Timestamps, Base):
    __tablename__ = "exchange_accounts"

    id: Mapped[uuid.UUID] = _pk()
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    exchange: Mapped[str] = mapped_column(String(32), server_default="binance")
    label: Mapped[str] = mapped_column(String(64))
    api_key_enc: Mapped[bytes] = mapped_column(LargeBinary)  # envelope-encrypted (SPEC 12)
    api_secret_enc: Mapped[bytes] = mapped_column(LargeBinary)
    key_type: Mapped[str] = mapped_column(String(16), server_default="HMAC")  # HMAC / Ed25519
    is_testnet: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    permissions_checked_at: Mapped[datetime | None] = _ts()


class RiskProfile(Timestamps, Base):
    """Defaults follow SPEC section 3."""

    __tablename__ = "risk_profiles"

    id: Mapped[uuid.UUID] = _pk()
    name: Mapped[str] = mapped_column(String(64), unique=True)
    risk_per_trade: Mapped[Decimal] = mapped_column(_num(), server_default="0.005")
    max_positions: Mapped[int] = mapped_column(Integer, server_default="4")
    max_symbol_exposure: Mapped[Decimal] = mapped_column(_num(), server_default="0.25")
    max_total_exposure: Mapped[Decimal] = mapped_column(_num(), server_default="0.80")
    max_open_risk: Mapped[Decimal] = mapped_column(_num(), server_default="0.02")
    max_bucket_risk: Mapped[Decimal] = mapped_column(_num(), server_default="0.0125")
    min_cash_reserve: Mapped[Decimal] = mapped_column(_num(), server_default="0.20")
    daily_loss: Mapped[Decimal] = mapped_column(_num(), server_default="0.02")
    weekly_loss: Mapped[Decimal] = mapped_column(_num(), server_default="0.05")
    max_dd: Mapped[Decimal] = mapped_column(_num(), server_default="0.12")
    max_leverage: Mapped[int] = mapped_column(Integer, server_default="1")

    __table_args__ = (
        CheckConstraint("risk_per_trade > 0 AND risk_per_trade <= 0.01", name="ck_risk_per_trade"),
        CheckConstraint("max_leverage BETWEEN 1 AND 3", name="ck_max_leverage"),
    )


class Bot(Timestamps, Base):
    __tablename__ = "bots"

    id: Mapped[uuid.UUID] = _pk()
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("exchange_accounts.id"))
    name: Mapped[str] = mapped_column(String(64))
    market: Mapped[Market] = mapped_column(_enum(Market))
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String(20)))
    status: Mapped[BotStatus] = mapped_column(_enum(BotStatus), server_default="DRAFT")
    mode: Mapped[BotMode] = mapped_column(_enum(BotMode), server_default="paper")
    risk_profile_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("risk_profiles.id"))


class StrategyConfig(Timestamps, Base):
    """Immutable versions: edit = insert a new version, never update in place."""

    __tablename__ = "strategy_configs"

    id: Mapped[uuid.UUID] = _pk()
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id"))
    strategy: Mapped[str] = mapped_column(String(8))  # S1..S4
    params: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    version: Mapped[int] = mapped_column(Integer)
    is_active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))

    __table_args__ = (UniqueConstraint("bot_id", "strategy", "version", name="uq_strategy_ver"),)


class Candle(Timestamps, Base):
    """Hypertable on ``open_time``. Only closed candles are stored."""

    __tablename__ = "candles"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    interval: Mapped[str] = mapped_column(String(8), primary_key=True)
    open_time: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    o: Mapped[Decimal] = mapped_column(_num())
    h: Mapped[Decimal] = mapped_column(_num())
    l: Mapped[Decimal] = mapped_column(_num())  # noqa: E741
    c: Mapped[Decimal] = mapped_column(_num())
    v: Mapped[Decimal] = mapped_column(_num())
    quote_v: Mapped[Decimal] = mapped_column(_num())
    trades: Mapped[int] = mapped_column(Integer)
    taker_buy_v: Mapped[Decimal] = mapped_column(_num())


class MarketMetric(Timestamps, Base):
    """Hypertable on ``ts``."""

    __tablename__ = "market_metrics"

    symbol: Mapped[str] = mapped_column(String(20), primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    funding_rate: Mapped[Decimal | None] = mapped_column(_num())
    open_interest: Mapped[Decimal | None] = mapped_column(_num())
    ls_ratio: Mapped[Decimal | None] = mapped_column(_num())
    fear_greed: Mapped[int | None] = mapped_column(Integer)


class Signal(Timestamps, Base):
    __tablename__ = "signals"

    id: Mapped[uuid.UUID] = _pk()
    bot_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("bots.id"))
    symbol: Mapped[str] = mapped_column(String(20))
    strategy: Mapped[str] = mapped_column(String(8))
    side: Mapped[Side] = mapped_column(_enum(Side))
    entry: Mapped[Decimal] = mapped_column(_num())
    stop: Mapped[Decimal] = mapped_column(_num())
    tp1: Mapped[Decimal | None] = mapped_column(_num())
    s_tech: Mapped[Decimal | None] = mapped_column(_num())
    s_ml: Mapped[Decimal | None] = mapped_column(_num())
    s_ai: Mapped[Decimal | None] = mapped_column(_num())
    score: Mapped[Decimal | None] = mapped_column(_num())
    decision: Mapped[Decision] = mapped_column(_enum(Decision))
    reject_reason: Mapped[str | None] = mapped_column(Text)


class AiAnalysis(Timestamps, Base):
    __tablename__ = "ai_analyses"

    id: Mapped[uuid.UUID] = _pk()
    symbol: Mapped[str | None] = mapped_column(String(20))
    kind: Mapped[AnalysisKind] = mapped_column(_enum(AnalysisKind))
    model: Mapped[str] = mapped_column(String(64))
    prompt_hash: Mapped[str] = mapped_column(String(64))
    input: Mapped[dict[str, Any]] = mapped_column(JSONB)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB)
    tokens_in: Mapped[int] = mapped_column(Integer, server_default="0")
    tokens_out: Mapped[int] = mapped_column(Integer, server_default="0")
    cost_usd: Mapped[Decimal] = mapped_column(_num(), server_default="0")
    latency_ms: Mapped[int] = mapped_column(Integer, server_default="0")


class NewsItem(Timestamps, Base):
    __tablename__ = "news_items"

    id: Mapped[uuid.UUID] = _pk()
    source: Mapped[str] = mapped_column(String(64))
    url: Mapped[str] = mapped_column(Text, unique=True)
    title: Mapped[str] = mapped_column(Text)
    published_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    symbols: Mapped[list[str]] = mapped_column(ARRAY(String(20)), server_default=text("'{}'"))
    sentiment: Mapped[Decimal | None] = mapped_column(_num())
    severity: Mapped[Decimal | None] = mapped_column(_num())
    category: Mapped[str | None] = mapped_column(String(32))


class Order(Timestamps, Base):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = _pk()
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id"))  # NULL = manual
    signal_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("signals.id"))
    client_order_id: Mapped[str] = mapped_column(String(64), unique=True)
    exchange_order_id: Mapped[str | None] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[Side] = mapped_column(_enum(Side))
    type: Mapped[str] = mapped_column(String(24))
    price: Mapped[Decimal | None] = mapped_column(_num())
    qty: Mapped[Decimal] = mapped_column(_num())
    status: Mapped[str] = mapped_column(String(24))
    leg: Mapped[OrderLeg] = mapped_column(_enum(OrderLeg))
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Fill(Timestamps, Base):
    __tablename__ = "fills"

    id: Mapped[uuid.UUID] = _pk()
    order_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("orders.id"))
    trade_id: Mapped[str] = mapped_column(String(64))
    price: Mapped[Decimal] = mapped_column(_num())
    qty: Mapped[Decimal] = mapped_column(_num())
    fee: Mapped[Decimal] = mapped_column(_num())
    fee_asset: Mapped[str] = mapped_column(String(16))
    is_maker: Mapped[bool] = mapped_column(Boolean)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    __table_args__ = (UniqueConstraint("order_id", "trade_id", name="uq_fill_trade"),)


class Position(Timestamps, Base):
    __tablename__ = "positions"

    id: Mapped[uuid.UUID] = _pk()
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id"))  # NULL = manual
    symbol: Mapped[str] = mapped_column(String(20))
    side: Mapped[Side] = mapped_column(_enum(Side))
    qty: Mapped[Decimal] = mapped_column(_num())
    avg_entry: Mapped[Decimal] = mapped_column(_num())
    stop: Mapped[Decimal | None] = mapped_column(_num())
    unrealized_pnl: Mapped[Decimal] = mapped_column(_num(), server_default="0")
    status: Mapped[PositionStatus] = mapped_column(_enum(PositionStatus))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = _ts()
    # execution bookkeeping (stop/TP order ids, trail version...): the whole execution.Position
    entry_cid: Mapped[str | None] = mapped_column(String(64), unique=True)
    state: Mapped[dict[str, Any] | None] = mapped_column(JSONB)


class Trade(Timestamps, Base):
    """One row per completed round trip."""

    __tablename__ = "trades"

    id: Mapped[uuid.UUID] = _pk()
    position_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("positions.id"), unique=True)
    pnl_usdt: Mapped[Decimal] = mapped_column(_num())
    pnl_r: Mapped[Decimal] = mapped_column(_num())
    fees: Mapped[Decimal] = mapped_column(_num())
    slippage: Mapped[Decimal] = mapped_column(_num())
    holding_minutes: Mapped[int] = mapped_column(Integer)
    exit_reason: Mapped[str] = mapped_column(String(32))


class EquitySnapshot(Timestamps, Base):
    """Hypertable on ``ts``; one row per minute."""

    __tablename__ = "equity_snapshots"

    account_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("exchange_accounts.id"), primary_key=True
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    equity: Mapped[Decimal] = mapped_column(_num())
    cash: Mapped[Decimal] = mapped_column(_num())
    exposure: Mapped[Decimal] = mapped_column(_num())
    drawdown: Mapped[Decimal] = mapped_column(_num())


class RiskEvent(Timestamps, Base):
    __tablename__ = "risk_events"

    id: Mapped[uuid.UUID] = _pk()
    bot_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("bots.id"))
    type: Mapped[str] = mapped_column(String(48))
    severity: Mapped[str] = mapped_column(String(16))
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    resolved_by: Mapped[str | None] = mapped_column(String(64))
    resolved_at: Mapped[datetime | None] = _ts()


class Backtest(Timestamps, Base):
    __tablename__ = "backtests"

    id: Mapped[uuid.UUID] = _pk()
    strategy_config_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB)
    range: Mapped[dict[str, Any]] = mapped_column(JSONB)
    fees_model: Mapped[dict[str, Any]] = mapped_column(JSONB)
    metrics: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    equity_curve_ref: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), server_default="PENDING")


class AuditLog(Timestamps, Base):
    """Append-only: a DB trigger (see migration) rejects UPDATE and DELETE."""

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(64))
    target: Mapped[str] = mapped_column(String(128))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    ip: Mapped[str | None] = mapped_column(String(64))
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
