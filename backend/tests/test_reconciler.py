from decimal import Decimal

from app.core.models import Side
from app.exchange.errors import ExchangeError
from app.exchange.orders import OrderInfo, OrderStatus, OrderType
from app.execution import ExecStatus
from app.execution.reconciler import Reconciler
from tests.exec_helpers import Env, make_env

D = Decimal


def recon(env: Env) -> Reconciler:
    return Reconciler(env.ex, env.store, env.mgr)


async def test_a_consistent_system_reports_nothing() -> None:
    env = make_env()
    await env.submit()
    rep = await recon(env).run_once()
    assert rep.ok and rep.positions_checked == 1 and rep.orders_checked >= 3
    assert "RECONCILE_MISMATCH" not in env.store.event_types()


async def test_empty_system_is_fine() -> None:
    rep = await recon(make_env()).run_once()
    assert rep.ok and rep.orders_checked == 0 and rep.positions_checked == 0


async def test_order_that_filled_while_we_were_not_looking_is_adopted() -> None:
    env = make_env()
    r = await env.submit(entry=D("95"), stop=D("93"), tp1=D(101))  # entry rests, gets cancelled
    assert r.status == ExecStatus.NOT_FILLED
    stale = OrderInfo(
        "st-stale", "BTCUSDT", Side.BUY, OrderType.LIMIT, OrderStatus.NEW, D(1), price=D(90)
    )
    await env.ex.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "st-stale", price=D(90))
    await env.store.record_order(stale, "ENTRY", None, None)  # our DB: still NEW
    env.ex.set_price("BTCUSDT", D(90))  # ...the exchange filled it
    rep = await recon(env).run_once()
    kinds = {m.kind for m in rep.mismatches}
    assert "ORDER_STATUS" in kinds
    assert env.store.orders["st-stale"][0].status == OrderStatus.FILLED  # Binance wins
    assert ("st-stale", "t1") in env.store.fills or any(k[0] == "st-stale" for k in env.store.fills)


async def test_order_missing_on_the_exchange_is_marked_cancelled() -> None:
    env = make_env()
    ghost = OrderInfo(
        "st-ghost", "BTCUSDT", Side.BUY, OrderType.LIMIT, OrderStatus.NEW, D(1), price=D(90)
    )
    await env.store.record_order(ghost, "ENTRY", None, None)
    rep = await recon(env).run_once()
    assert [m.kind for m in rep.mismatches] == ["ORDER_MISSING"]
    assert env.store.orders["st-ghost"][0].status == OrderStatus.CANCELED


async def test_our_orders_unknown_to_the_db_are_adopted_but_foreign_orders_are_left_alone() -> None:
    env = make_env()
    await env.ex.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "st-orphan", price=D(90))
    await env.ex.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "by-hand", price=D(90))
    rep = await recon(env).run_once()
    assert [m.kind for m in rep.mismatches] == ["ORDER_UNKNOWN"]
    assert "st-orphan" in env.store.orders and "by-hand" not in env.store.orders


async def test_a_filled_position_that_lost_its_stop_is_re_protected() -> None:
    """The crash window: filled, record saved, process died before the stop was placed."""
    env = make_env()
    r = await env.submit()
    assert r.position is not None
    await env.ex.cancel_all_orders("BTCUSDT")  # exits vanish (crash / manual cancel)
    assert env.open_order_types() == [] and env.ex.holding("BTC") > 0

    rep = await recon(env).run_once()
    unprotected = [m for m in rep.mismatches if m.kind == "UNPROTECTED"]
    assert (
        len(unprotected) == 1 and unprotected[0].critical and "re-placed" in unprotected[0].action
    )
    assert env.ex.locked("BTC") == env.ex.holding("BTC") > 0  # covered again
    assert "STOP_LOSS_LIMIT:SELL" in env.open_order_types()
    crit = [
        e
        for e in env.store.events
        if e["type"] == "RECONCILE_MISMATCH" and e["payload"]["kind"] == "UNPROTECTED"
    ]
    assert len(crit) == 1 and crit[0]["severity"] == "critical"
    assert (await recon(env).run_once()).ok  # and it stays fixed


async def test_if_the_stop_cannot_be_re_placed_the_position_is_closed() -> None:
    env = make_env()
    await env.submit()
    await env.ex.cancel_all_orders("BTCUSDT")
    env.ex.fail_next("place_oco_sell", ExchangeError("down"), times=10)
    rep = await recon(env).run_once()
    assert any(m.kind == "UNPROTECTED" and "closed" in m.action for m in rep.mismatches)
    assert env.ex.holding("BTC") == 0 and await env.store.get_position("BTCUSDT") is None


async def test_exit_that_filled_while_we_were_down_is_settled() -> None:
    env = make_env()
    await env.submit()
    env.ex.set_price("BTCUSDT", D("97.9"))  # the stop fills; nobody called sync_position
    rep = await recon(env).run_once()
    assert rep.positions_checked == 1
    assert await env.store.get_position("BTCUSDT") is None
    assert env.store.trades and env.store.trades[0]["reason"] == "stop"


async def test_position_the_exchange_no_longer_holds_is_closed_in_our_records() -> None:
    env = make_env()
    r = await env.submit()
    assert r.position is not None
    await env.ex.cancel_all_orders("BTCUSDT")
    env.ex._free["BTC"] = D(0)  # sold by hand outside the bot
    rep = await recon(env).run_once()
    assert any(m.kind == "POSITION_GONE" for m in rep.mismatches)
    assert await env.store.get_position("BTCUSDT") is None


async def test_quantity_drift_adopts_the_exchange_quantity() -> None:
    env = make_env()
    r = await env.submit()
    assert r.position is not None
    env.ex._locked["BTC"] -= D(5)  # 5 coins left the account behind our back
    rep = await recon(env).run_once()
    assert any(m.kind == "POSITION_QTY" for m in rep.mismatches)
    assert r.position.qty == env.ex.holding("BTC")  # exchange truth wins


async def test_exchange_errors_are_reported_and_feed_the_breakers_without_crashing() -> None:
    from app.risk import BreakerKind
    from tests.risk_helpers import NOW

    env = make_env()
    await env.submit()
    env.ex.fail_next("open_orders", ExchangeError("503"), times=20)
    rep = await recon(env).run_once()
    assert rep.errors and not rep.ok  # reported, not raised
    assert BreakerKind.API_ERRORS not in {b.kind for b in env.risk.breakers.active(NOW)}
    for _ in range(3):  # a sick API keeps failing: the breaker trips
        await recon(env).run_once()
    assert BreakerKind.API_ERRORS in {b.kind for b in env.risk.breakers.active(NOW)}


async def test_run_forever_survives_crashes_and_keeps_looping() -> None:
    env = make_env()
    rec = recon(env)
    calls = {"n": 0}
    original = rec.run_once

    async def flaky() -> object:
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("unexpected")
        return await original()

    rec.run_once = flaky  # type: ignore[method-assign,assignment]

    class Stop(Exception):
        pass

    async def sleep(_: float) -> None:
        if calls["n"] >= 3:
            raise Stop

    try:
        await rec.run_forever(60, sleep)
    except Stop:
        pass
    assert calls["n"] == 3  # kept running after the crash
