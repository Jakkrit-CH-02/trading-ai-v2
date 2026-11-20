from datetime import UTC, datetime, timedelta
from decimal import Decimal

from app.exchange.types import INTERVAL_MS, Kline

T0 = datetime(2025, 1, 1, tzinfo=UTC)


def make_kline(i: int, interval: str = "1h", symbol: str = "BTCUSDT", closed: bool = True) -> Kline:
    """Candle number ``i`` counted from T0 (deterministic prices)."""
    price = Decimal(100 + i)
    return Kline(
        symbol=symbol,
        interval=interval,
        open_time=T0 + timedelta(milliseconds=INTERVAL_MS[interval] * i),
        o=price,
        h=price + 1,
        l=price - 1,
        c=price + Decimal("0.5"),
        v=Decimal(10),
        quote_v=Decimal(1000),
        trades=5,
        taker_buy_v=Decimal(4),
        is_closed=closed,
    )


def at(i: int, interval: str = "1h") -> datetime:
    return T0 + timedelta(milliseconds=INTERVAL_MS[interval] * i)
