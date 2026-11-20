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


async def backtest(args: argparse.Namespace) -> int:
    from decimal import Decimal

    from app.backtest.data import load_market_frames
    from app.backtest.engine import BacktestConfig, FeeModel
    from app.backtest.metrics import compute_metrics, evaluate_gate1
    from app.backtest.montecarlo import monte_carlo
    from app.backtest.registry import make_strategy, run_strategy
    from app.backtest.report import (
        coverage_warning,
        format_gate,
        format_metrics,
        format_monte_carlo,
        format_walk_forward,
    )
    from app.backtest.walkforward import walk_forward

    configure_logging("backtest")
    cfg = BacktestConfig(
        fees=FeeModel(taker=Decimal(str(args.fee)), slippage=Decimal(str(args.slippage))),
        min_quote_volume_24h=args.min_quote_volume,
    )
    end = datetime.now(UTC)
    start = end - timedelta(days=int(args.years * 365.25))
    engine = make_engine()
    try:
        store = PgCandleStore(make_session_factory(engine))
        data = await load_market_frames(store, args.symbol, start, end)
    except ValueError as e:
        print(f"error: {e}")
        return 1
    finally:
        await engine.dispose()

    print(f"{args.strategy} {args.symbol}  fee={args.fee} slippage={args.slippage}")
    warn = coverage_warning(data.frames["1h"].index)
    if warn:
        print(f"  WARNING: {warn}")

    if args.walk_forward:
        grid: dict[str, list[float | int]] = {}
        for item in args.grid or []:
            key, _, values = item.partition("=")
            grid[key] = [float(v) if "." in v else int(v) for v in values.split(",")]
        try:
            wf = walk_forward(args.strategy, data, grid, cfg)
        except ValueError as e:
            print(f"error: {e}")
            return 1
        print(format_walk_forward(wf))
        print(format_gate(evaluate_gate1(wf.oos_metrics)))
        print(format_monte_carlo(monte_carlo(wf.oos_trades)))
        return 0

    strategy = make_strategy(args.strategy)
    feats = strategy.prepare(data)
    res = run_strategy(strategy, feats, cfg)
    m = compute_metrics(res.trades, res.equity, float(res.initial_equity))
    print("  (single run over the whole range — in-sample; use --walk-forward for gate 1)")
    print(format_metrics(m))
    print(format_gate(evaluate_gate1(m)))
    print(format_monte_carlo(monte_carlo(res.trades)))
    skipped = sum(1 for r in res.signals if r.decision.value != "TAKEN")
    print(f"  signals           {len(res.signals)} total, {skipped} skipped/rejected")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="softtrade")
    sub = parser.add_subparsers(dest="cmd", required=True)
    bf = sub.add_parser("backfill", help="download historical candles (resumable, idempotent)")
    bf.add_argument("--symbols", nargs="+", help="default: configured symbols")
    bf.add_argument("--intervals", nargs="+", help="default: configured intervals")
    bf.add_argument("--years", type=float, default=3.0)
    bf.add_argument("--days", type=int, help="overrides --years (handy for small test runs)")
    bt = sub.add_parser("backtest", help="event-driven backtest on stored candles")
    bt.add_argument("--strategy", required=True, choices=["s1", "s2", "s3", "s4"])
    bt.add_argument("--symbol", default="BTCUSDT")
    bt.add_argument("--years", type=float, default=3.0)
    bt.add_argument("--fee", type=float, default=0.001, help="taker fee per fill")
    bt.add_argument("--slippage", type=float, default=0.0005, help="per side")
    bt.add_argument("--min-quote-volume", type=float, default=50_000_000.0)
    bt.add_argument("--walk-forward", action="store_true")
    bt.add_argument("--grid", nargs="*", help="walk-forward grid, e.g. tp1_r=1.2,1.5,2.0")
    args = parser.parse_args(argv)

    s = get_settings()
    if args.cmd == "backfill":
        days = args.days if args.days is not None else int(args.years * 365)
        return asyncio.run(backfill(args.symbols or s.symbols, args.intervals or s.intervals, days))
    if args.cmd == "backtest":
        return asyncio.run(backtest(args))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
