"""Execution-layer types."""

import enum
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from app.risk.types import RiskDecision


class ExecStatus(enum.StrEnum):
    REJECTED = "REJECTED"  # Risk Engine said no (nothing was sent)
    DUPLICATE = "DUPLICATE"  # same client order id already handled (safe retry)
    NOT_FILLED = "NOT_FILLED"  # entry timed out and was cancelled; no position
    PROTECTED = "PROTECTED"  # filled and an exchange-side stop is in place
    EMERGENCY_CLOSED = "EMERGENCY_CLOSED"  # stop could not be placed in time: position closed
    UNPROTECTED = "UNPROTECTED"  # CRITICAL: position open without a stop and close failed


def make_client_order_id(bot_id: str | None, signal_id: str | None, leg: str) -> str:
    """Deterministic and idempotent (retrying the same signal yields the same id).

    Binance limits ids to 36 chars of ``[A-Za-z0-9-_]``. ULIDs are 26 chars each, so the
    SPEC's ``st-{botId}-{signalId}-{leg}`` would overflow; a 20-hex digest of both keeps it
    unique, deterministic and within the limit.
    """
    digest = hashlib.sha1(f"{bot_id}:{signal_id}".encode(), usedforsecurity=False).hexdigest()[:20]
    cid = f"st{digest}-{leg}"
    if len(cid) > 36 or not all(c.isalnum() or c in "-_" for c in cid):
        raise ValueError(f"invalid client order id {cid!r}")
    return cid


@dataclass(slots=True)
class Position:
    symbol: str
    bot_id: str | None
    signal_id: str | None
    strategy: str
    qty0: Decimal  # protectable quantity at entry (after base-asset fees)
    qty: Decimal  # still open
    avg_entry: Decimal
    stop: Decimal
    tp1: Decimal | None
    entry_cid: str
    opened_at: datetime
    entry_cost: Decimal = Decimal(0)  # USDT paid for the entry incl. fees
    base_asset: str = ""
    order_cids: list[str] = field(default_factory=list)  # every order of this position
    initial_stop: Decimal = Decimal(0)
    stop_cids: list[str] = field(default_factory=list)  # live stop-loss legs
    tp_cid: str | None = None
    tp1_done: bool = False
    tp1_close_fraction: Decimal = Decimal("0.5")
    protected: bool = False
    version: int = 0  # bumps every time stops are (re)placed -> unique client ids
    closed: bool = False
    exit_reason: str = ""


@dataclass(frozen=True, slots=True)
class ExecutionResult:
    status: ExecStatus
    decision: RiskDecision | None = None
    position: Position | None = None
    detail: str = ""
    client_order_id: str | None = None


@dataclass(frozen=True, slots=True)
class KillReport:
    cancelled_orders: int
    closed_positions: int
    failures: tuple[str, ...]
