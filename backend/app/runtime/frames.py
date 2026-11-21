"""Live features: the same ``prepare`` as the backtest, run on a trailing window of closed
candles read from the store. ``evaluate`` then judges the newest bar only."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta

import structlog

from app.backtest.data import BTC
from app.exchange.types import INTERVAL_MS
from app.marketdata.indicators import klines_to_frame
from app.marketdata.store import CandleStore
from app.ml.features import with_ml_features
from app.strategies.base import MarketFrames, Strategy
from app.strategies.features import Features

log = structlog.get_logger()

# Long enough that recursive indicators (EMA200 on 4h, Wilder smoothing) and the 90-day
# percentile windows have converged, so a window gives the same numbers as full history.
WINDOW_BARS = {"1h": 6000, "4h": 1500}


class DataGap(Exception):
    """The candles needed to judge this bar are missing or late: do not trade on a guess."""


def _floor(t: datetime, ms: int) -> datetime:
    return datetime.fromtimestamp(t.timestamp() // (ms / 1000) * (ms / 1000), tz=t.tzinfo)


async def load_features(
    store: CandleStore,
    strategy: Strategy,
    symbol: str,
    bar_open: datetime,
    wait_s: float = 0.0,
    poll_s: float = 2.0,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    with_ml: bool = False,
) -> Features:
    """Features whose last bar is the closed bar that opened at ``bar_open``.

    Higher-timeframe bars that close at the same instant (a 4h bar closing with the 12:00
    1h bar) are part of the backtest's view of that bar, so we wait for them (up to
    ``wait_s``) rather than judging the bar with a stale regime."""
    exec_iv = strategy.exec_interval
    bar_end = bar_open + timedelta(milliseconds=INTERVAL_MS[exec_iv])
    needs = [(symbol, "1h"), (symbol, "4h")]
    if symbol != BTC:
        needs.append((BTC, "4h"))
    waited = 0.0
    while True:
        frames: dict[str, object] = {}
        stale: list[str] = []
        for sym, iv in needs:
            ms = INTERVAL_MS[iv]
            last_open = _floor(bar_end, ms) - timedelta(milliseconds=ms)
            start = last_open - timedelta(milliseconds=ms * (WINDOW_BARS[iv] - 1))
            ks = await store.load(sym, iv, start, last_open)
            if not ks or ks[-1].open_time != last_open:
                stale.append(f"{sym} {iv} (want {last_open:%Y-%m-%d %H:%M})")
                continue
            frames[f"{sym}:{iv}"] = klines_to_frame(ks)
        if not stale:
            break
        if waited >= wait_s:
            raise DataGap("missing candles: " + ", ".join(stale))
        await sleep(poll_s)
        waited += poll_s
    own = {iv: frames[f"{symbol}:{iv}"] for iv in ("1h", "4h")}
    btc = frames.get(f"{BTC}:4h") if symbol != BTC else None
    data = MarketFrames(symbol, own, btc)  # type: ignore[arg-type]
    feats = strategy.prepare(data)
    if with_ml:  # the same ml_* columns the backtest adds (app.ml.features)
        feats = with_ml_features(feats, data)
    if feats.time(len(feats) - 1) != bar_open:
        raise DataGap(f"{symbol} {exec_iv}: newest bar is not {bar_open:%Y-%m-%d %H:%M}")
    return feats
