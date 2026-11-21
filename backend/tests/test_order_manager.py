from decimal import Decimal
from typing import Any

import pytest

from app.core.models import Side
from app.exchange.errors import ExchangeError, IPBanned, OrderRejected, RateLimited
from app.exchange.orders import OrderStatus, OrderType
from app.execution import ExecStatus, make_client_order_id
from app.risk import BreakerKind, Reason
from tests.exec_helpers import BOT, SIG, Env, LostResponseExchange, make_env
from tests.risk_helpers import FILTERS, NOW, make_engine, make_intent, make_market, make_portfolio

D = Decimal


def block_market_sells(env: Env) -> None:
    """The exchange refuses every market SELL (the emergency exit) but accepts everything else."""
    original = env.ex.place_order

    async def guarded(*a: Any, **k: Any) -> Any:
        if a[1] == Side.SELL and a[2] == OrderType.MARKET:
            raise OrderRejected("cannot sell now")
        return await original(*a, **k)

    env.ex.place_order = guarded  # type: ignore[method-assign]


# ---- ids ----


def test_client_order_ids_fit_binance_limits_and_are_deterministic() -> None:
    a = make_client_order_id(BOT, SIG, "e")
    assert a == make_client_order_id(BOT, SIG, "e")  # same signal -> same id (idempotent retry)
    assert len(a) <= 36 and a.startswith("st")
    assert a != make_client_order_id(BOT, SIG, "r1") != make_client_order_id(BOT, "other", "r1")
    assert len(make_client_order_id(None, None, "o12")) <= 36
    with pytest.raises(ValueError, match="invalid client order id"):
        make_client_order_id(BOT, SIG, "bad leg!")


# ---- happy path ----


async def test_filled_entry_is_immediately_protected_by_exchange_side_orders() -> None:
    env = make_env()
    r = await env.submit()
    assert r.status == ExecStatus.PROTECTED and r.position is not None and r.position.protected
    # OCO (take-profit + stop) for half, plus a stop for the runner: nothing is unprotected
    assert env.open_order_types() == [
        "LIMIT_MAKER:SELL",
        "STOP_LOSS_LIMIT:SELL",
        "STOP_LOSS_LIMIT:SELL",
    ]
    held = env.ex.holding("BTC")
    assert held == env.ex.locked("BTC") > 0  # every coin is locked behind a stop
    assert r.position.qty == held == r.position.qty0
    # the stop sits at the risk-approved price, with the limit just below the trigger
    stops = [o for o in env.ex.orders.values() if o.type == OrderType.STOP_LOSS_LIMIT]
    assert {o.stop_price for o in stops} == {D(98)} and {o.price for o in stops} == {D("97.80")}


async def test_exits_cover_the_whole_position_with_50_percent_taken_at_tp1() -> None:
    env = make_env()
    r = await env.submit()
    assert r.position is not None
    tp = env.ex.orders[("BTCUSDT", r.position.tp_cid or "")]
    assert tp.price == D(105) and abs(tp.qty - r.position.qty / 2) <= D("0.00001")
    stops = [env.ex.orders[("BTCUSDT", c)] for c in r.position.stop_cids]
    assert len(stops) == 2 and sum((o.qty for o in stops), D(0)) == r.position.qty  # all covered


async def test_entry_that_rests_as_maker_fills_later_and_is_then_protected() -> None:
    env = make_env()
    env.clock.hooks.append(lambda t: env.ex.set_price("BTCUSDT", D("99.5")) if t >= 2 else None)
    r = await env.submit(entry=D("99.5"), stop=D("97.5"), tp1=D(104))
    assert r.status == ExecStatus.PROTECTED and r.position is not None
    assert r.position.avg_entry == D("99.50")


async def test_unfilled_entry_is_cancelled_not_chased() -> None:
    env = make_env()
    r = await env.submit(entry=D("95"), stop=D("93"), tp1=D(101))  # never reaches 95
    assert r.status == ExecStatus.NOT_FILLED and r.position is None
    assert env.ex.orders[("BTCUSDT", r.client_order_id or "")].status == OrderStatus.CANCELED
    assert env.open_order_types() == [] and env.ex.locked("USDT") == 0
    assert env.clock.t >= 5  # waited the whole timeout, then gave up
    assert [c[0] for c in env.ex.calls].count("place_order") == 1  # no second, higher bid


# ---- risk first ----


async def test_a_rejected_order_never_reaches_the_exchange() -> None:
    env = make_env()
    r = await env.submit(stop=D(0))
    assert r.status == ExecStatus.REJECTED and r.decision is not None
    assert Reason.NO_STOP in r.decision.reasons
    assert not any(c[0] == "place_order" for c in env.ex.calls)
    assert "ORDER_REJECTED" in env.store.event_types()


async def test_manual_orders_get_no_shortcut() -> None:
    env = make_env()
    r = await env.submit(is_manual=True, stop=D(0))
    assert r.status == ExecStatus.REJECTED and not env.ex.orders


async def test_position_size_is_set_by_the_risk_engine_not_the_caller() -> None:
    env = make_env()
    r = await env.submit()
    assert r.decision is not None and r.position is not None
    assert r.position.qty0 == r.decision.qty
    assert r.decision.risk_amount <= D(10_000) * D("0.005")


async def test_only_one_position_per_symbol() -> None:
    env = make_env()
    await env.submit()
    r2 = await env.submit(signal_id="01CCCCCCCCCCCCCCCCCCCCCCCC")
    assert r2.status == ExecStatus.REJECTED and "already open" in r2.detail


# ---- idempotency and ambiguous failures ----


async def test_resubmitting_the_same_signal_never_double_trades() -> None:
    env = make_env()
    first = await env.submit(entry=D("95"), stop=D("93"), tp1=D(101))
    again = await env.submit(entry=D("95"), stop=D("93"), tp1=D(101))
    assert first.status == ExecStatus.NOT_FILLED and again.status == ExecStatus.DUPLICATE
    assert len(env.ex.orders) == 1


async def test_send_failure_is_retried_with_the_same_id() -> None:
    env = make_env()
    env.ex.fail_next("place_order", ExchangeError("503"), times=1)  # fails before reaching the book
    r = await env.submit()
    assert r.status == ExecStatus.PROTECTED
    entries = [o for o in env.ex.orders.values() if o.side == Side.BUY]
    assert len(entries) == 1  # not two entries


async def test_lost_response_does_not_cause_a_second_order() -> None:
    from app.execution import ExecConfig, InMemoryExecutionStore, OrderManager

    ex = LostResponseExchange({"BTCUSDT": D(100)}, {"USDT": D(10_000)}, FILTERS)
    store = InMemoryExecutionStore()
    mgr = OrderManager(ex, make_engine(), store, ExecConfig(entry_timeout_s=2), now=lambda: NOW)
    r = await mgr.submit(make_intent(bot_id=BOT, signal_id=SIG), make_portfolio(), make_market())
    assert r.status == ExecStatus.PROTECTED
    assert len([o for o in ex.orders.values() if o.side == Side.BUY]) == 1  # found it by client id


async def test_intent_is_stored_before_it_is_sent() -> None:
    env = make_env()
    env.ex.fail_next("place_order", ExchangeError("down"), times=5)
    r = await env.submit()
    assert r.status == ExecStatus.NOT_FILLED
    cid = make_client_order_id(BOT, SIG, "e")
    assert await env.store.has_order(cid)  # a crash here would still leave a trace
    again = await env.submit()
    assert again.status == ExecStatus.DUPLICATE


# ---- the 3-second stop rule ----


async def test_failing_to_place_the_stop_closes_the_position_at_market() -> None:
    env = make_env()
    env.ex.fail_next("place_oco_sell", ExchangeError("stop endpoint down"), times=5)
    r = await env.submit()
    assert r.status == ExecStatus.EMERGENCY_CLOSED
    assert env.ex.holding("BTC") == 0 and env.open_order_types() == []  # flat, nothing dangling
    assert "STOP_PLACEMENT_FAILED" in env.store.event_types()
    assert env.store.trades and env.store.trades[0]["reason"] == "emergency_close"
    assert await env.store.get_position("BTCUSDT") is None


async def test_stop_not_confirmed_within_the_deadline_closes_the_position() -> None:
    env = make_env(use_virtual_monotonic=False, stop_deadline_s=0.2)
    env.ex.delays["place_oco_sell"] = 5.0  # the exchange is hanging
    r = await env.submit()
    assert r.status == ExecStatus.EMERGENCY_CLOSED
    assert env.ex.holding("BTC") == 0


async def test_partial_stop_placement_is_torn_down_before_closing() -> None:
    env = make_env()
    # OCO succeeds, the runner stop fails: half protection must not linger or lock the coins
    env.ex.fail_next("place_order", ExchangeError("boom"), times=0)
    original = env.ex.place_order
    calls = {"n": 0}

    async def flaky(*a: object, **k: object):  # type: ignore[no-untyped-def]
        if a[2] == OrderType.STOP_LOSS_LIMIT:
            raise ExchangeError("runner stop failed")
        calls["n"] += 1
        return await original(*a, **k)  # type: ignore[arg-type]

    env.ex.place_order = flaky  # type: ignore[method-assign]
    r = await env.submit()
    assert r.status == ExecStatus.EMERGENCY_CLOSED
    assert env.ex.holding("BTC") == 0 and env.open_order_types() == []


async def test_if_even_the_emergency_exit_fails_the_position_is_flagged_unprotected() -> None:
    env = make_env()
    env.ex.fail_next("place_oco_sell", ExchangeError("down"), times=10)
    block_market_sells(env)
    r = await env.submit()
    assert r.status == ExecStatus.UNPROTECTED and r.position is not None
    assert env.ex.holding("BTC") > 0  # we really are stuck holding it
    assert "UNPROTECTED_POSITION" in env.store.event_types()
    assert (
        next(e for e in env.store.events if e["type"] == "UNPROTECTED_POSITION")["severity"]
        == "critical"
    )
    blocked = await env.submit(signal_id="01DDDDDDDDDDDDDDDDDDDDDDDD", symbol="ETHUSDT")
    assert blocked.status == ExecStatus.REJECTED  # entries frozen while a position is naked


async def test_unprotected_position_freezes_all_new_entries_via_the_breaker() -> None:
    env = make_env()
    env.ex.fail_next("place_oco_sell", ExchangeError("down"), times=10)
    block_market_sells(env)
    await env.submit()
    kinds = {b.kind for b in env.risk.breakers.active(NOW)}
    assert BreakerKind.EXCHANGE_EVENT in kinds


# ---- partial fills, fees, dust ----


async def test_partial_fill_cancels_the_rest_and_protects_only_what_filled() -> None:
    env = make_env()
    env.ex.partial_fill_ratio = D("0.4")
    moved: list[float] = []

    def touch_once(t: float) -> None:
        if t >= 2 and not moved:  # the market touches our bid once, filling 40%, then moves away
            moved.append(t)
            env.ex.set_price("BTCUSDT", D("99.5"))
            env.ex.prices["BTCUSDT"] = D("100.5")

    env.clock.hooks.append(touch_once)
    r = await env.submit(entry=D("99.5"), stop=D("97.5"), tp1=D(104))
    assert r.status == ExecStatus.PROTECTED and r.position is not None and r.decision is not None
    assert r.decision.qty * D("0.35") < r.position.qty < r.decision.qty * D("0.45")
    entry = env.ex.orders[("BTCUSDT", r.position.entry_cid)]
    assert entry.status == OrderStatus.CANCELED  # the unfilled remainder was cancelled, not chased
    assert env.ex.locked("BTC") == env.ex.holding("BTC") == r.position.qty
    assert env.ex.locked("USDT") == 0


async def test_partial_market_fill_is_protected_at_the_filled_size() -> None:
    env = make_env()
    env.ex.partial_fill_ratio = D("0.4")
    r = await env.submit(order_type="MARKET", expected_slippage_bps=D(5))
    assert r.status == ExecStatus.PROTECTED and r.position is not None and r.decision is not None
    assert r.position.qty < r.decision.qty * D("0.5")
    assert env.ex.locked("BTC") == env.ex.holding("BTC") == r.position.qty  # exactly what we own
    assert env.ex.locked("USDT") == 0  # the unfilled reservation was released


async def test_fee_taken_in_base_asset_is_deducted_before_sizing_the_stop() -> None:
    env = make_env(fee_in_base=True)
    r = await env.submit()
    assert r.status == ExecStatus.PROTECTED and r.position is not None
    fills = await env.ex.fills("BTCUSDT", r.position.entry_cid)
    assert fills[0].fee_asset == "BTC"
    held = env.ex.holding("BTC")
    # protected quantity is the net coins rounded down to the step: never more than we own
    assert r.position.qty <= held and held - r.position.qty < FILTERS.step_size
    assert env.ex.locked("BTC") == r.position.qty
    assert r.position.qty < r.decision.qty


async def test_a_dust_sized_fill_is_not_pretended_to_be_protected() -> None:
    env = make_env()
    env.ex.partial_fill_ratio = D("0.0001")
    r = await env.submit(order_type="MARKET", expected_slippage_bps=D(5))
    assert r.status == ExecStatus.NOT_FILLED and "minimum" in r.detail
    assert "DUST_FILL" in env.store.event_types()


# ---- managing the position ----


async def test_tp1_fill_moves_the_runner_stop_to_breakeven_plus_fees() -> None:
    env = make_env()
    r = await env.submit()
    assert r.position is not None
    pos = r.position
    env.ex.set_price("BTCUSDT", D(105))
    events = await env.mgr.sync_position("BTCUSDT")
    assert events == ["TP1_FILLED", "STOP_MOVED_TO_BREAKEVEN"]
    assert pos.tp1_done and pos.stop == D("100.20")  # entry 100 x (1 + 2 x 0.1%)
    open_orders = [o for o in env.ex.orders.values() if o.status.is_open]
    assert len(open_orders) == 1 and open_orders[0].stop_price == D("100.20")
    assert abs(open_orders[0].qty - pos.qty) <= D("0.00001") and env.ex.locked("BTC") == pos.qty


async def test_stop_hit_closes_records_the_loss_and_starts_the_cooldown() -> None:
    env = make_env()
    r = await env.submit()
    env.ex.set_price("BTCUSDT", D("97.9"))  # trigger 98 reached, limit 97.80 still fillable
    events = await env.mgr.sync_position("BTCUSDT")
    assert events == ["CLOSED_STOP"]
    assert await env.store.get_position("BTCUSDT") is None
    trade = env.store.trades[0]
    assert trade["reason"] == "stop" and trade["pnl"] < 0 and D("-1.4") < trade["pnl_r"] < D("-0.9")
    assert env.ex.holding("BTC") == 0 and env.open_order_types() == []
    # a loss feeds the circuit-breaker streak and blocks re-entry for 4 hours
    assert env.mgr.cooldowns["BTCUSDT"] > NOW
    again = await env.submit(signal_id="01EEEEEEEEEEEEEEEEEEEEEEEE")
    assert again.status == ExecStatus.REJECTED and Reason.COOLDOWN in again.decision.reasons
    assert r.status == ExecStatus.PROTECTED


async def test_price_gapping_through_the_stop_limit_triggers_a_market_exit() -> None:
    env = make_env()
    await env.submit()
    env.ex.set_price("BTCUSDT", D(90))  # far below the stop-limit: stops are triggered but unfilled
    assert env.ex.holding("BTC") > 0
    events = await env.mgr.sync_position("BTCUSDT")
    assert events == [f"EMERGENCY_{ExecStatus.EMERGENCY_CLOSED}"]
    assert env.ex.holding("BTC") == 0 and "STOP_GAPPED" in env.store.event_types()


async def test_sync_does_nothing_for_unknown_symbols_and_quiet_positions() -> None:
    env = make_env()
    assert await env.mgr.sync_position("ETHUSDT") == []
    await env.submit()
    assert await env.mgr.sync_position("BTCUSDT") == []
    assert len([o for o in env.ex.orders.values() if o.status.is_open]) == 3


async def test_trailing_stop_only_moves_up_and_keeps_the_position_covered() -> None:
    env = make_env()
    r = await env.submit()
    assert r.position is not None
    env.ex.set_price("BTCUSDT", D("103"))
    assert await env.mgr.raise_stop("BTCUSDT", D("101")) is True
    assert r.position.stop == D("101") and env.ex.locked("BTC") == env.ex.holding("BTC") > 0
    assert {o.stop_price for o in env.ex.orders.values() if o.status.is_open and o.stop_price} == {
        D("101")
    }
    assert await env.mgr.raise_stop("BTCUSDT", D("100")) is False  # never loosen
    assert await env.mgr.raise_stop("BTCUSDT", D("103")) is False  # not below the market
    assert await env.mgr.raise_stop("ETHUSDT", D("1")) is False
    assert r.position.stop == D("101")
    # rejected updates must leave the position exactly as it was: open, with its stop live
    assert not r.position.closed and r.position.protected
    assert env.ex.locked("BTC") == env.ex.holding("BTC") == r.position.qty
    assert {o.stop_price for o in env.ex.orders.values() if o.status.is_open and o.stop_price} == {
        D("101")
    }


async def test_failed_stop_replacement_closes_the_position_rather_than_leave_it_naked() -> None:
    env = make_env()
    r = await env.submit()
    env.ex.set_price("BTCUSDT", D("103"))
    env.ex.fail_next("place_oco_sell", ExchangeError("down"), times=10)
    assert await env.mgr.raise_stop("BTCUSDT", D("101")) is False
    assert env.ex.holding("BTC") == 0 and r.position is not None and r.position.closed


# ---- circuit breakers fed by API health ----


async def test_rate_limit_response_pauses_new_entries() -> None:
    env = make_env()
    env.ex.fail_next("place_order", RateLimited(30))
    r = await env.submit()
    assert r.status == ExecStatus.NOT_FILLED
    assert BreakerKind.RATE_LIMIT in {b.kind for b in env.risk.breakers.active(NOW)}
    blocked = await env.submit(signal_id="01FFFFFFFFFFFFFFFFFFFFFFFF")
    assert (
        blocked.status == ExecStatus.REJECTED and Reason.BREAKER_ACTIVE in blocked.decision.reasons
    )


async def test_ip_ban_stops_immediately() -> None:
    env = make_env()
    env.ex.fail_next("place_order", IPBanned(300))
    await env.submit()
    assert BreakerKind.IP_BAN in {b.kind for b in env.risk.breakers.active(NOW)}


async def test_repeated_api_errors_trip_the_error_breaker() -> None:
    env = make_env()
    env.ex.fail_next("get_order", ExchangeError("flaky"), times=20)
    env.ex.fail_next("place_order", ExchangeError("flaky"), times=10)
    await env.submit()
    assert BreakerKind.API_ERRORS in {b.kind for b in env.risk.breakers.active(NOW)}


# ---- kill switch ----


async def test_kill_switch_cancels_everything_flattens_and_blocks_new_entries() -> None:
    env = make_env()
    await env.submit()
    assert env.ex.holding("BTC") > 0 and env.open_order_types()
    report = await env.mgr.kill_all("operator pressed the button")
    assert report.failures == () and report.closed_positions == 1 and report.cancelled_orders == 3
    assert env.ex.holding("BTC") == 0 and env.open_order_types() == []
    assert "KILL_SWITCH" in env.store.event_types()
    blocked = await env.submit(signal_id="01GGGGGGGGGGGGGGGGGGGGGGGG")
    assert blocked.status == ExecStatus.REJECTED and Reason.KILL_SWITCH in blocked.decision.reasons
    env.risk.breakers.reset_kill(totp_verified=True)
    assert (await env.submit(signal_id="01HHHHHHHHHHHHHHHHHHHHHHHH")).status == ExecStatus.PROTECTED


async def test_kill_switch_latches_first_even_if_the_exchange_is_failing() -> None:
    env = make_env()
    await env.submit()
    env.ex.fail_next("cancel_all_orders", ExchangeError("down"), times=10)
    env.ex.fail_next("open_orders", ExchangeError("down"), times=1)
    report = await env.mgr.kill_all("drawdown")
    assert env.risk.breakers.kill_switch_active  # new entries are impossible regardless
    assert report.failures and "cancel BTCUSDT" in " ".join(report.failures)


async def test_kill_switch_with_nothing_open_is_a_clean_no_op() -> None:
    env = make_env()
    report = await env.mgr.kill_all("test")
    assert (report.cancelled_orders, report.closed_positions, report.failures) == (0, 0, ())
    assert env.risk.breakers.kill_switch_active


# ---- leaving a position on purpose (time stop, false breakout) -----------------------------


async def test_close_position_sells_at_market_after_freeing_the_coins_and_records_the_reason() -> (
    None
):
    env = make_env()
    await env.submit()
    assert await env.mgr.close_position("BTCUSDT", "time_stop") is True
    assert await env.store.get_position("BTCUSDT") is None
    assert env.open_order_types() == [] and env.ex.holding("BTC") == 0
    trade = env.store.trades[-1]
    assert trade["reason"] == "time_stop" and "POSITION_CLOSED" in env.store.event_types()


async def test_close_position_does_not_sell_twice_when_the_stop_filled_first() -> None:
    env = make_env()
    await env.submit()
    env.ex.set_price("BTCUSDT", D("97.9"))  # the exchange-side stop triggers and fills
    assert await env.mgr.close_position("BTCUSDT", "time_stop") is True
    assert [t["reason"] for t in env.store.trades] == ["stop"]  # booked as what really happened
    sells = [
        o for o in env.ex.orders.values() if o.type == OrderType.MARKET and o.side == Side.SELL
    ]
    assert sells == []


async def test_a_failed_exit_puts_the_stop_back_instead_of_leaving_the_position_naked() -> None:
    env = make_env()
    await env.submit()
    block_market_sells(env)
    assert await env.mgr.close_position("BTCUSDT", "false_breakout") is False
    pos = await env.store.get_position("BTCUSDT")
    assert pos is not None and pos.protected
    assert any(t.startswith("STOP_LOSS_LIMIT") for t in env.open_order_types())
    assert "EXIT_FAILED" in env.store.event_types()


async def test_close_position_on_nothing_is_a_no_op() -> None:
    assert await make_env().mgr.close_position("BTCUSDT", "time_stop") is False


async def test_a_trailing_only_signal_gets_a_stop_but_no_take_profit_order() -> None:
    env = make_env()
    r = await env.submit(place_tp=False)  # S3: tp1 only feeds the R:R check
    assert r.status == ExecStatus.PROTECTED and r.position is not None
    assert r.position.tp1 is None and r.position.tp_cid is None
    assert env.open_order_types() == ["STOP_LOSS_LIMIT:SELL"]


async def test_a_full_target_strategy_sells_everything_at_the_target() -> None:
    env = make_env()
    r = await env.submit(tp1_close_fraction=D(1))  # S2: TP1 is the whole exit
    assert r.position is not None and r.position.tp1_close_fraction == D(1)
    assert sorted(env.open_order_types()) == ["LIMIT_MAKER:SELL", "STOP_LOSS_LIMIT:SELL"]
    env.ex.set_price("BTCUSDT", D(106))
    assert await env.mgr.sync_position("BTCUSDT") == ["CLOSED_TP1"]
    assert env.ex.holding("BTC") == 0
