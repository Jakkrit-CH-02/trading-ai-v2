"""``softtrade testnet-check``: verify the testnet adapter against the real Binance Spot
Demo/Testnet. Everything here uses fake money on ``demo-api.binance.com`` or
``testnet.binance.vision`` only (the adapter refuses any other host).
Credentials come from the environment and are never printed.

Stages: 1) read-only (clock, filters, balances)   2) resting order lifecycle (place, read,
cancel)   3) full protected-position lifecycle through the real OrderManager."""

import asyncio
from decimal import Decimal

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.models import BotStatus, Side
from app.exchange.binance_testnet import ENVIRONMENTS, BinanceTestnetAdapter
from app.exchange.orders import OrderType
from app.execution import ExecConfig, ExecStatus, InMemoryExecutionStore, OrderManager
from app.risk import MarketState, PortfolioState, RiskEngine, RiskProfile, TradeIntent
from app.risk.engine import round_price
from app.risk.sizing import quantize_down

SYMBOL = "BTCUSDT"


def say(msg: str) -> None:
    print(msg, flush=True)


async def run(stage: int) -> int:
    s = get_settings()
    configure_logging("testnet-check")
    key, secret = s.binance_api_key.get_secret_value(), s.binance_api_secret.get_secret_value()
    if not key or not secret:
        say("BINANCE_API_KEY / BINANCE_API_SECRET are not set (testnet keys go in .env)")
        return 1
    base = ENVIRONMENTS[s.binance_trading_env]
    say(f"environment: {s.binance_trading_env} ({base})")
    ex = BinanceTestnetAdapter(key, secret, base_url=base)
    try:
        # ---- stage 1: read-only ----
        drift = await ex.sync_time()
        say(f"[1] clock drift vs Binance: {drift:+.0f} ms (limit 500)")
        f = await ex.symbol_filters(SYMBOL)
        say(
            f"[1] {SYMBOL} filters: tick={f.tick_size} step={f.step_size} "
            f"min_qty={f.min_qty} min_notional={f.min_notional}"
        )
        bal = await ex.balances()
        say("[1] balances: " + ", ".join(f"{a}={b.free}" for a, b in sorted(bal.items())[:8]))
        price = await ex.last_price(SYMBOL)
        say(f"[1] {SYMBOL} last price: {price}")
        if stage < 2:
            return 0

        # ---- stage 2: a resting order that cannot fill ----
        qty = quantize_down(max(f.min_qty, (f.min_notional * 3) / price), f.step_size)
        far = round_price(price * Decimal("0.7"), f.tick_size)  # inside the PERCENT_PRICE band
        cid = "st-check-rest"
        o = await ex.place_order(SYMBOL, Side.BUY, OrderType.LIMIT, qty, cid, price=far)
        say(f"[2] placed resting LIMIT BUY {qty} @ {far}: status={o.status}")
        got = await ex.get_order(SYMBOL, cid)
        say(f"[2] read it back: status={got.status} executed={got.executed_qty}")
        c = await ex.cancel_order(SYMBOL, cid)
        say(f"[2] cancelled: status={c.status}")
        if stage < 3:
            return 0

        # ---- stage 3: the real OrderManager, entry + exchange-side stop ----
        store = InMemoryExecutionStore()
        risk = RiskEngine(RiskProfile())
        mgr = OrderManager(ex, risk, store, ExecConfig(entry_timeout_s=15, poll_interval_s=1))
        from datetime import UTC, datetime

        now = datetime.now(UTC)
        risk.breakers.record_tick(now)
        usdt = bal["USDT"].free if "USDT" in bal else Decimal(0)
        port = PortfolioState(usdt, usdt, usdt, usdt, usdt)
        market = MarketState(now, BotStatus.PAPER, 0.5, abs(drift))
        stop = round_price(price * Decimal("0.98"), f.tick_size)
        tp1 = round_price(price * Decimal("1.06"), f.tick_size)
        entry = round_price(price * Decimal("1.001"), f.tick_size)  # marketable: fills at once
        intent = TradeIntent(
            SYMBOL,
            Side.BUY,
            entry,
            stop,
            "testnet-check",
            tp1,
            "LIMIT",
            signal_id="check1",
            bot_id="check",
        )
        r = await mgr.submit(intent, port, market)
        say(f"[3] submit -> {r.status}: {r.detail}")
        if r.position is not None:
            live = await ex.open_orders(SYMBOL)
            say(
                "[3] exchange-side orders: "
                + ", ".join(f"{o.type}:{o.side}@{o.stop_price or o.price}" for o in live)
            )
        await mgr.kill_all("testnet-check cleanup")
        left = await ex.open_orders(SYMBOL)
        say(f"[3] cleaned up; open orders left: {len(left)}")
        return (
            0
            if r.status in (ExecStatus.PROTECTED, ExecStatus.NOT_FILLED, ExecStatus.REJECTED)
            else 2
        )
    finally:
        await ex.aclose()


def main(stage: int) -> int:
    return asyncio.run(run(stage))
