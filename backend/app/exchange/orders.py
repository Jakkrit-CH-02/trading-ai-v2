"""Order-side types shared by every trading adapter (live, testnet, fake)."""

import enum
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from app.core.models import Side


class OrderStatus(enum.StrEnum):
    NEW = "NEW"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELED = "CANCELED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"

    @property
    def is_open(self) -> bool:
        return self in (OrderStatus.NEW, OrderStatus.PARTIALLY_FILLED)


class OrderType(enum.StrEnum):
    LIMIT = "LIMIT"
    LIMIT_MAKER = "LIMIT_MAKER"
    MARKET = "MARKET"
    STOP_LOSS_LIMIT = "STOP_LOSS_LIMIT"


@dataclass(frozen=True, slots=True)
class OrderInfo:
    client_order_id: str
    symbol: str
    side: Side
    type: OrderType
    status: OrderStatus
    qty: Decimal
    executed_qty: Decimal = Decimal(0)
    price: Decimal | None = None
    stop_price: Decimal | None = None
    avg_price: Decimal | None = None  # volume-weighted fill price
    exchange_order_id: str | None = None
    order_list_id: str | None = None  # set for OCO legs
    ts: datetime | None = None


@dataclass(frozen=True, slots=True)
class Fill:
    client_order_id: str
    symbol: str
    trade_id: str
    price: Decimal
    qty: Decimal
    fee: Decimal
    fee_asset: str
    is_maker: bool
    ts: datetime


@dataclass(frozen=True, slots=True)
class Balance:
    asset: str
    free: Decimal
    locked: Decimal = Decimal(0)

    @property
    def total(self) -> Decimal:
        return self.free + self.locked
