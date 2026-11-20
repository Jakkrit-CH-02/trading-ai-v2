"""The fake exchange must be faithful, or the order-manager tests prove nothing."""

from decimal import Decimal

import pytest

from app.core.models import Side
from app.exchange.errors import ExchangeError, OrderRejected, UnknownOrder
from app.exchange.fake import FakeTradingExchange
from app.exchange.orders import OrderStatus, OrderType
from tests.risk_helpers import FILTERS

D = Decimal


def ex(price: str = "100", usdt: int = 10_000, **kw: object) -> FakeTradingExchange:
    return FakeTradingExchange({"BTCUSDT": D(price)}, {"USDT": D(usdt)}, FILTERS, **kw)  # type: ignore[arg-type]


async def test_buy_locks_quote_and_fill_moves_balances_and_charges_fee() -> None:
    e = ex()
    o = await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(10), "a", price=D(99))
    assert o.status == OrderStatus.NEW and e.locked("USDT") > D(990)
    e.set_price("BTCUSDT", D(99))
    o = await e.get_order("BTCUSDT", "a")
    assert o.status == OrderStatus.FILLED and o.avg_price == D(99)
    assert e.free("BTC") == 10 and e.locked("USDT") == 0
    assert e.free("USDT") == D(10_000) - D(990) - D("0.99")  # cost + 0.1% fee, reservation released
    [fill] = await e.fills("BTCUSDT", "a")
    assert fill.fee == D("0.99") and fill.fee_asset == "USDT" and fill.is_maker


async def test_cancel_releases_the_reservation() -> None:
    e = ex()
    await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(10), "a", price=D(90))
    await e.cancel_order("BTCUSDT", "a")
    assert e.locked("USDT") == 0 and e.free("USDT") == 10_000


async def test_insufficient_balance_and_filters_are_enforced() -> None:
    e = ex(usdt=100)
    with pytest.raises(OrderRejected, match="insufficient"):
        await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(10), "a", price=D(99))
    e = ex()
    with pytest.raises(OrderRejected, match="LOT_SIZE"):
        await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D("0.000001"), "b", price=D(99))
    with pytest.raises(OrderRejected, match="PRICE_FILTER"):
        await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "c", price=D("99.005"))
    with pytest.raises(OrderRejected, match="MIN_NOTIONAL"):
        await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D("0.01"), "d", price=D(99))


async def test_duplicate_client_order_id_is_rejected_like_binance() -> None:
    e = ex()
    await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "dup", price=D(90))
    with pytest.raises(OrderRejected, match="Duplicate") as err:
        await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "dup", price=D(90))
    assert err.value.code == -2010
    assert len(e.orders) == 1


async def test_limit_maker_that_would_take_is_rejected_and_marketable_limit_fills_as_taker() -> (
    None
):
    e = ex()
    with pytest.raises(OrderRejected, match="immediately match"):
        await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT_MAKER, D(1), "m", price=D(101))
    o = await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "t", price=D(101))
    assert o.status == OrderStatus.FILLED and o.avg_price == D(100)  # filled at the market, not 101
    assert not (await e.fills("BTCUSDT", "t"))[0].is_maker


async def test_market_order_slippage_and_partial_ioc() -> None:
    e = ex()
    e.market_slippage = D("0.01")
    o = await e.place_order("BTCUSDT", Side.BUY, OrderType.MARKET, D(1), "m")
    assert o.avg_price == D("101")
    e.partial_fill_ratio = D("0.5")
    p = await e.place_order("BTCUSDT", Side.BUY, OrderType.MARKET, D(10), "p")
    assert p.status == OrderStatus.CANCELED and D(4) < p.executed_qty < D(6)  # rest cancelled
    assert e.locked("USDT") == 0


async def _long(e: FakeTradingExchange, qty: int = 10) -> None:
    await e.place_order("BTCUSDT", Side.BUY, OrderType.MARKET, D(qty), "buy")


async def test_sell_locks_base_so_a_second_stop_on_the_same_coins_is_rejected() -> None:
    e = ex()
    await _long(e)
    await e.place_order(
        "BTCUSDT",
        Side.SELL,
        OrderType.STOP_LOSS_LIMIT,
        D(10),
        "s1",
        price=D("97.8"),
        stop_price=D(98),
    )
    assert e.locked("BTC") == 10 and e.free("BTC") == 0
    with pytest.raises(OrderRejected, match="insufficient"):
        await e.place_order(
            "BTCUSDT",
            Side.SELL,
            OrderType.STOP_LOSS_LIMIT,
            D(10),
            "s2",
            price=D("97.8"),
            stop_price=D(98),
        )


async def test_stop_limit_fills_when_price_stays_above_the_limit() -> None:
    e = ex()
    await _long(e)
    await e.place_order(
        "BTCUSDT",
        Side.SELL,
        OrderType.STOP_LOSS_LIMIT,
        D(10),
        "s",
        price=D("97.8"),
        stop_price=D(98),
    )
    e.set_price("BTCUSDT", D("97.9"))  # between trigger (98) and limit (97.8): fills at the limit
    o = await e.get_order("BTCUSDT", "s")
    assert o.status == OrderStatus.FILLED and o.avg_price == D("97.8")
    assert e.holding("BTC") == 0


async def test_gap_through_the_stop_limit_leaves_the_stop_triggered_but_unfilled() -> None:
    e = ex()
    await _long(e)
    await e.place_order(
        "BTCUSDT",
        Side.SELL,
        OrderType.STOP_LOSS_LIMIT,
        D(10),
        "s",
        price=D("97.8"),
        stop_price=D(98),
    )
    e.set_price("BTCUSDT", D(90))
    o = await e.get_order("BTCUSDT", "s")
    assert o.status == OrderStatus.NEW  # the dangerous "protected but not really" state
    assert e.holding("BTC") == 10
    e.set_price("BTCUSDT", D("97.85"))  # recovers above the limit: now it fills
    assert (await e.get_order("BTCUSDT", "s")).status == OrderStatus.FILLED


async def test_oco_locks_once_and_one_filled_leg_cancels_the_other() -> None:
    e = ex()
    await _long(e)
    legs = await e.place_oco_sell("BTCUSDT", D(10), D(105), D(98), D("97.8"), "oco")
    assert [x.client_order_id for x in legs] == ["oco-tp", "oco-sl"]
    assert e.locked("BTC") == 10  # one lock for both legs
    e.set_price("BTCUSDT", D(105))
    assert (await e.get_order("BTCUSDT", "oco-tp")).status == OrderStatus.FILLED
    assert (await e.get_order("BTCUSDT", "oco-sl")).status == OrderStatus.CANCELED
    assert e.locked("BTC") == 0 and e.holding("BTC") == 0


async def test_oco_stop_leg_fill_cancels_the_take_profit() -> None:
    e = ex()
    await _long(e)
    await e.place_oco_sell("BTCUSDT", D(10), D(105), D(98), D("97.8"), "oco")
    e.set_price("BTCUSDT", D("97.9"))
    assert (await e.get_order("BTCUSDT", "oco-sl")).status == OrderStatus.FILLED
    assert (await e.get_order("BTCUSDT", "oco-tp")).status == OrderStatus.CANCELED
    assert e.locked("BTC") == 0


async def test_oco_price_relationship_and_duplicates() -> None:
    e = ex()
    await _long(e)
    with pytest.raises(OrderRejected, match="relationship"):
        await e.place_oco_sell("BTCUSDT", D(10), D(99), D(98), D("97.8"), "bad")  # TP below market
    await e.place_oco_sell("BTCUSDT", D(5), D(105), D(98), D("97.8"), "ok")
    with pytest.raises(OrderRejected, match="Duplicate"):
        await e.place_oco_sell("BTCUSDT", D(5), D(105), D(98), D("97.8"), "ok")


async def test_cancel_unknown_order_and_get_unknown_order() -> None:
    e = ex()
    with pytest.raises(UnknownOrder):
        await e.get_order("BTCUSDT", "nope")
    with pytest.raises(UnknownOrder):
        await e.cancel_order("BTCUSDT", "nope")
    await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "x", price=D(90))
    await e.cancel_order("BTCUSDT", "x")
    with pytest.raises(OrderRejected, match="Unknown order"):  # already cancelled
        await e.cancel_order("BTCUSDT", "x")


async def test_cancel_all_and_open_orders_listing() -> None:
    e = ex()
    await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "a", price=D(90))
    await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "b", price=D(91))
    assert len(await e.open_orders()) == 2 == len(await e.open_orders("BTCUSDT"))
    assert len(await e.cancel_all_orders("BTCUSDT")) == 2
    assert await e.open_orders() == [] and e.locked("USDT") == 0


async def test_fee_in_base_asset_reduces_the_coins_received() -> None:
    e = ex(fee_in_base=True)
    await e.place_order("BTCUSDT", Side.BUY, OrderType.MARKET, D(10), "b")
    assert e.free("BTC") == D(10) - D("0.01")  # 0.1% of the coins
    [f] = await e.fills("BTCUSDT", "b")
    assert f.fee_asset == "BTC" and f.fee == D("0.01")


async def test_failure_injection_and_latency_hooks_and_balances() -> None:
    e = ex()
    e.fail_next("place_order", ExchangeError("boom"))
    with pytest.raises(ExchangeError, match="boom"):
        await e.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "a", price=D(90))
    await e.place_order(
        "BTCUSDT", Side.BUY, OrderType.LIMIT, D(1), "a", price=D(90)
    )  # next one works
    e.delays["balances"] = 0.001
    bal = await e.balances()
    assert bal["USDT"].total == D(10_000) and bal["USDT"].locked > 0
    assert await e.last_price("BTCUSDT") == D(100)
    assert (await e.symbol_filters("BTCUSDT")) == FILTERS
    assert [c[0] for c in e.calls][:2] == ["place_order", "place_order"]
