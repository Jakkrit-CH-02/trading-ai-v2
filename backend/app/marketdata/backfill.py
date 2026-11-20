"""Gap detection, gap filling and historical backfill — one mechanism.

``fill_gaps`` compares the candles we have with the candles that *should* exist in a
range and fetches only the missing runs. Backfill is ``fill_gaps`` over a long range, so
it is resumable and idempotent; reconnect recovery is ``fill_gaps`` over a short one.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import structlog

from app.exchange.base import ExchangeAdapter
from app.exchange.types import INTERVAL_MS, dt_to_ms, ms_to_dt
from app.marketdata.store import CandleStore

log = structlog.get_logger()

PAGE = 1000


@dataclass(frozen=True, slots=True)
class FillResult:
    missing: int  # candles that were missing before the run
    inserted: int  # candles actually stored
    unavailable: int  # still missing afterwards (exchange had no data, e.g. before listing)


def floor_to_interval(dt: datetime, interval: str) -> datetime:
    step = INTERVAL_MS[interval]
    return ms_to_dt(dt_to_ms(dt) // step * step)


def last_closed_open_time(now: datetime, interval: str) -> datetime:
    """open_time of the most recent candle that has fully closed at ``now``."""
    return floor_to_interval(now, interval) - timedelta(milliseconds=INTERVAL_MS[interval])


def expected_open_times(start: datetime, end: datetime, interval: str) -> list[datetime]:
    step = INTERVAL_MS[interval]
    s, e = dt_to_ms(floor_to_interval(start, interval)), dt_to_ms(floor_to_interval(end, interval))
    return [ms_to_dt(t) for t in range(s, e + 1, step)]


def find_gaps(
    present: set[datetime], start: datetime, end: datetime, interval: str
) -> list[tuple[datetime, datetime]]:
    """Contiguous runs ``(first_missing, last_missing)`` of open_times absent from ``present``."""
    step = timedelta(milliseconds=INTERVAL_MS[interval])
    runs: list[tuple[datetime, datetime]] = []
    run_start: datetime | None = None
    prev: datetime | None = None
    for t in expected_open_times(start, end, interval):
        if t in present:
            continue
        if run_start is None:
            run_start = prev = t
        elif prev is not None and t - prev == step:
            prev = t
        else:
            runs.append((run_start, prev or run_start))
            run_start = prev = t
    if run_start is not None:
        runs.append((run_start, prev or run_start))
    return runs


async def fill_gaps(
    adapter: ExchangeAdapter,
    store: CandleStore,
    symbol: str,
    interval: str,
    start: datetime,
    end: datetime | None = None,
) -> FillResult:
    """Fetch and store every closed candle in [start, end] that is not already stored."""
    now = await adapter.server_time()
    last = last_closed_open_time(now, interval)
    end = min(end, last) if end is not None else last
    start = floor_to_interval(start.astimezone(UTC), interval)
    if start > end:
        return FillResult(0, 0, 0)

    present = await store.open_times(symbol, interval, start, end)
    gaps = find_gaps(present, start, end, interval)
    missing = sum(len(expected_open_times(a, b, interval)) for a, b in gaps)
    step = timedelta(milliseconds=INTERVAL_MS[interval])

    inserted = 0
    for gap_start, gap_end in gaps:
        cursor = gap_start
        while cursor <= gap_end:
            page = await adapter.get_klines(symbol, interval, start=cursor, end=gap_end, limit=PAGE)
            if not page:
                break  # nothing more available in this run
            inserted += await store.save(page)
            cursor = page[-1].open_time + step
    after = find_gaps(await store.open_times(symbol, interval, start, end), start, end, interval)
    unavailable = sum(len(expected_open_times(a, b, interval)) for a, b in after)
    log.info(
        "marketdata.fill_gaps",
        symbol=symbol,
        interval=interval,
        missing=missing,
        inserted=inserted,
        unavailable=unavailable,
    )
    return FillResult(missing=missing, inserted=inserted, unavailable=unavailable)
