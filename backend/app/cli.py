"""``softtrade`` command line. Subcommands are added per phase (backfill now; backtest in
Phase 2; kill in Phase 3/7)."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.db import make_engine, make_session_factory
from app.core.logging import configure_logging
from app.exchange import BinancePublicAdapter
from app.exchange.errors import IPBanned, RateLimited
from app.marketdata.backfill import fill_gaps
from app.marketdata.store import PgCandleStore


async def backfill(symbols: list[str], intervals: list[str], days: int) -> int:
    s = get_settings()
    configure_logging("backfill")
    engine = make_engine()
    adapter = BinancePublicAdapter(s.binance_rest_url, s.binance_ws_url)
    store = PgCandleStore(make_session_factory(engine))
    start = datetime.now(UTC) - timedelta(days=days)
    try:
        for symbol in symbols:
            for interval in intervals:
                try:
                    res = await fill_gaps(adapter, store, symbol, interval, start)
                except (RateLimited, IPBanned) as e:
                    print(f"stopped: {e}")
                    return 2
                print(
                    f"{symbol} {interval}: missing={res.missing} inserted={res.inserted} "
                    f"unavailable={res.unavailable}"
                )
    finally:
        await adapter.aclose()
        await engine.dispose()
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="softtrade")
    sub = parser.add_subparsers(dest="cmd", required=True)
    bf = sub.add_parser("backfill", help="download historical candles (resumable, idempotent)")
    bf.add_argument("--symbols", nargs="+", help="default: configured symbols")
    bf.add_argument("--intervals", nargs="+", help="default: configured intervals")
    bf.add_argument("--years", type=float, default=3.0)
    bf.add_argument("--days", type=int, help="overrides --years (handy for small test runs)")
    args = parser.parse_args(argv)

    s = get_settings()
    if args.cmd == "backfill":
        days = args.days if args.days is not None else int(args.years * 365)
        return asyncio.run(backfill(args.symbols or s.symbols, args.intervals or s.intervals, days))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
