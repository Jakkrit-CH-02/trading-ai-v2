"""``softtrade`` command line. Subcommands are added per phase (backfill now; backtest in
Phase 2; kill in Phase 3/7)."""

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

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
    if args.symbols:
        return await _pooled(args, cfg, start, end, engine)
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


async def _pooled(
    args: argparse.Namespace, cfg: Any, start: datetime, end: datetime, engine: Any
) -> int:
    from app.backtest.data import load_market_frames
    from app.backtest.metrics import evaluate_gate1
    from app.backtest.montecarlo import monte_carlo
    from app.backtest.report import format_gate, format_metrics, format_monte_carlo
    from app.backtest.walkforward import pool_walk_forward, walk_forward

    grid: dict[str, list[float | int]] = {}
    for item in args.grid or []:
        key, _, values = item.partition("=")
        grid[key] = [float(v) if "." in v else int(v) for v in values.split(",")]
    results = []
    try:
        store = PgCandleStore(make_session_factory(engine))
        print(f"{args.strategy} pooled over {', '.join(args.symbols)}  (equal weight)")
        for sym in args.symbols:
            try:
                data = await load_market_frames(store, sym, start, end)
                wf = walk_forward(args.strategy, data, grid, cfg)
            except ValueError as e:
                print(f"  {sym}: skipped ({e})")
                continue
            m = wf.oos_metrics
            print(
                f"  {sym:<9} trades {m.n_trades:>3}  PF {m.profit_factor:5.2f}  "
                f"expectancy {m.expectancy_r:+.2f}R  net {m.net_pnl:+.0f}"
            )
            results.append(wf)
    finally:
        await engine.dispose()
    if not results:
        return 1
    trades, _equity, metrics = pool_walk_forward(results, float(cfg.initial_equity))
    print("\n  POOLED OUT-OF-SAMPLE — the only numbers that count:")
    print(format_metrics(metrics))
    print(format_gate(evaluate_gate1(metrics)))
    print(format_monte_carlo(monte_carlo(trades)))
    return 0


async def create_user_cmd(email: str) -> int:
    import getpass

    from app.auth.core import totp_uri
    from app.auth.crypto import CryptoError
    from app.auth.routes import create_user
    from app.main import build_services

    password = getpass.getpass("Password (min 12 chars): ")
    if len(password) < 12 or password != getpass.getpass("Repeat: "):
        print("password too short or does not match")
        return 2
    svc = build_services(get_settings())
    try:
        _, secret = await create_user(svc, email, password)
    except CryptoError as e:
        print(f"{e}")
        return 2
    print("User created. Add this to your authenticator app (shown once):")
    print(f"  secret: {secret}\n  uri:    {totp_uri(secret, email.lower())}")
    return 0


async def ml_train(args: argparse.Namespace) -> int:
    from app.ml.pipeline import train_and_register
    from app.ml.train import TrainConfig

    configure_logging("ml")
    engine = make_engine()
    sessions = make_session_factory(engine)
    try:
        try:
            r = await train_and_register(
                sessions, PgCandleStore(sessions), args.strategy.lower(), args.symbols, args.years,
                TrainConfig(optuna_trials=args.trials),
            )  # fmt: skip
        except ValueError as e:
            print(f"{args.strategy}: no model trained - {e}")
            return 1

        def f(d: dict[str, float]) -> dict[str, float]:
            return {k: round(v, 3) for k, v in d.items() if v == v}

        print(f"{r.n_signals} labelled signals")
        print(f"cross-validation (purged walk-forward): {f(r.cv)}")
        print(f"holdout (never trained on):             {f(r.holdout)}")
        print(f"out-of-sample backtest baseline: {r.baseline}")
        print(f"out-of-sample backtest with ML:  {r.with_ml}")
        print(f"backtest: {r.backtest_summary}")
        state = "PROMOTED to active" if r.promoted else "stored as candidate"
        print(f"model v{r.version}: {state} ({r.reason})")
    finally:
        await engine.dispose()
    return 0


async def ml_status() -> int:
    from sqlalchemy import select

    from app.core.models import MlModel

    engine = make_engine()
    try:
        async with make_session_factory(engine)() as db:
            for m in (
                await db.execute(select(MlModel).order_by(MlModel.strategy, MlModel.version))
            ).scalars():
                h = (m.metrics or {}).get("holdout") or {}
                span = f"{m.trained_from:%Y-%m-%d}..{m.trained_to:%Y-%m-%d}"
                auc = h.get("auc")
                print(f"{m.strategy} v{m.version} {m.status:9} n={m.n_samples} AUC={auc} {span}")
    finally:
        await engine.dispose()
    return 0


async def ml_rollback(strategy: str) -> int:
    from app.ml.registry import rollback

    engine = make_engine()
    try:
        m = await rollback(make_session_factory(engine), strategy.upper())
        print(f"{strategy.upper()}: now v{m.version}" if m else "nothing to roll back to")
        return 0 if m else 1
    finally:
        await engine.dispose()


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
    bt.add_argument(
        "--symbols", nargs="+", help="pooled equal-weight walk-forward over these symbols"
    )
    bt.add_argument("--years", type=float, default=3.0)
    bt.add_argument("--fee", type=float, default=0.001, help="taker fee per fill")
    bt.add_argument("--slippage", type=float, default=0.0005, help="per side")
    bt.add_argument("--min-quote-volume", type=float, default=50_000_000.0)
    bt.add_argument("--walk-forward", action="store_true")
    bt.add_argument("--grid", nargs="*", help="walk-forward grid, e.g. tp1_r=1.2,1.5,2.0")
    tc = sub.add_parser("testnet-check", help="verify the adapter against the Binance Spot Testnet")
    tc.add_argument(
        "--stage", type=int, choices=[1, 2, 3], default=1, help="1 read-only, 2 +order, 3 +manager"
    )
    cu = sub.add_parser("create-user", help="create the (only) login; prints the TOTP secret once")
    cu.add_argument("--email", required=True)
    sub.add_parser("gen-master-key", help="print a new MASTER_KEY for .env")
    mt = sub.add_parser("ml-train", help="train the S_ml model; promote only if it earns it")
    mt.add_argument("--strategy", required=True, choices=["s1", "s2", "s3"])
    mt.add_argument(
        "--symbols", nargs="+", default=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]
    )
    mt.add_argument("--years", type=float, default=3.0)
    mt.add_argument("--trials", type=int, default=25, help="Optuna trials")
    sub.add_parser("ml-status", help="list stored ML models and their status")
    mr = sub.add_parser("ml-rollback", help="re-activate the previous ML model version")
    mr.add_argument("--strategy", required=True, choices=["s1", "s2", "s3"])
    args = parser.parse_args(argv)

    s = get_settings()
    if args.cmd == "backfill":
        days = args.days if args.days is not None else int(args.years * 365)
        return asyncio.run(backfill(args.symbols or s.symbols, args.intervals or s.intervals, days))
    if args.cmd == "testnet-check":
        from app.testnet_check import main as check

        return check(args.stage)
    if args.cmd == "backtest":
        return asyncio.run(backtest(args))
    if args.cmd == "ml-train":
        return asyncio.run(ml_train(args))
    if args.cmd == "ml-status":
        return asyncio.run(ml_status())
    if args.cmd == "ml-rollback":
        return asyncio.run(ml_rollback(args.strategy))
    if args.cmd == "gen-master-key":
        from app.auth.crypto import generate_master_key

        print(generate_master_key())
        return 0
    if args.cmd == "create-user":
        return asyncio.run(create_user_cmd(args.email))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
