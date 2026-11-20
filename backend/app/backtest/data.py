"""Load candles from the store into the frames strategies consume."""

from datetime import datetime

from app.marketdata.indicators import klines_to_frame
from app.marketdata.store import CandleStore
from app.strategies.base import MarketFrames

BTC = "BTCUSDT"


async def load_market_frames(
    store: CandleStore,
    symbol: str,
    start: datetime,
    end: datetime,
    intervals: tuple[str, ...] = ("1h", "4h"),
) -> MarketFrames:
    """Closed candles for ``symbol`` plus BTC 4h as the market filter (SPEC 2.1)."""
    frames = {}
    for interval in intervals:
        klines = await store.load(symbol, interval, start, end)
        if not klines:
            raise ValueError(
                f"no {interval} candles for {symbol} between {start:%Y-%m-%d} and "
                f"{end:%Y-%m-%d}; run `softtrade backfill` first"
            )
        frames[interval] = klines_to_frame(klines)
    btc_4h = None
    if symbol != BTC:
        btc = await store.load(BTC, "4h", start, end)
        if btc:
            btc_4h = klines_to_frame(btc)
    return MarketFrames(symbol, frames, btc_4h)
