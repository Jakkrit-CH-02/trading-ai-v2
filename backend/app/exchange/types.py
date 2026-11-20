"""Exchange-neutral market data types. Prices/quantities are ``Decimal`` — never float."""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

INTERVAL_MS: dict[str, int] = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}


def ms_to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def dt_to_ms(dt: datetime) -> int:
    return int(dt.timestamp() * 1000)


@dataclass(frozen=True, slots=True)
class Kline:
    symbol: str
    interval: str
    open_time: datetime  # UTC
    o: Decimal
    h: Decimal
    l: Decimal  # noqa: E741
    c: Decimal
    v: Decimal
    quote_v: Decimal
    trades: int
    taker_buy_v: Decimal
    is_closed: bool = True


@dataclass(frozen=True, slots=True)
class BookTicker:
    symbol: str
    bid: Decimal
    bid_qty: Decimal
    ask: Decimal
    ask_qty: Decimal
    ts: datetime  # local receive time (Binance spot bookTicker has no event time)


MarketEvent = Kline | BookTicker
