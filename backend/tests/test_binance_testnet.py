"""Testnet adapter against a mocked HTTP layer (no network, no credentials)."""

import json
import logging
from decimal import Decimal
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from app.core.logging import configure_logging
from app.core.models import Side
from app.exchange.binance_testnet import BinanceTestnetAdapter, fmt, sign
from app.exchange.errors import (
    ExchangeError,
    IPBanned,
    LiveTradingForbidden,
    OrderRejected,
    RateLimited,
    UnknownOrder,
)
from app.exchange.orders import OrderStatus, OrderType

D = Decimal
KEY, SECRET = "test-key-AAAA", "test-secret-BBBB"


def adapter(handler: Any, **kw: Any) -> tuple[BinanceTestnetAdapter, list[httpx.Request]]:
    seen: list[httpx.Request] = []

    def wrapped(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        response: httpx.Response = handler(req)
        return response

    client = httpx.AsyncClient(transport=httpx.MockTransport(wrapped))
    return BinanceTestnetAdapter(KEY, SECRET, client=client, **kw), seen


def form(req: httpx.Request) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(req.content.decode()).items()}


ORDER = {
    "symbol": "BTCUSDT",
    "orderId": 77,
    "clientOrderId": "st-a",
    "price": "100.00000000",
    "origQty": "2.00000000",
    "executedQty": "1.00000000",
    "cummulativeQuoteQty": "100.00000000",
    "status": "PARTIALLY_FILLED",
    "type": "LIMIT",
    "side": "BUY",
    "stopPrice": "0.00000000",
    "updateTime": 1_750_000_000_000,
    "orderListId": -1,
}


# ---- signing and safety rails ----


def test_signature_matches_the_binance_documentation_vector() -> None:
    secret = "NhqPtmdSJYdKjVHjA7PZj4Mge3R5YNiP1e3UZjInClVN65XAbvqqM6A7H5fATj0j"
    q = (
        "symbol=LTCBTC&side=BUY&type=LIMIT&timeInForce=GTC&quantity=1&price=0.1"
        "&recvWindow=5000&timestamp=1499827319559"
    )
    assert sign(secret, q) == "c8db56825ae71d6d79447849e617115f4a920fa2acdcab2b053c4b2838bd6b71"


@pytest.mark.parametrize(
    "url",
    [
        "https://api.binance.com",  # mainnet
        "https://api1.binance.com",
        "https://data-api.binance.vision",
        "https://testnet.binance.vision.evil.com",  # look-alike hosts
        "https://demo-api.binance.com.evil.com",
        "https://evil-demo-api.binance.com",
        "http://demo-api.binance.com",  # no TLS
        "http://testnet.binance.vision",  # no TLS
        "https://evil.com/testnet.binance.vision",
        "https://fapi.binance.com",
    ],
)
def test_refuses_any_host_that_is_not_demo_or_testnet(url: str) -> None:
    with pytest.raises(LiveTradingForbidden):
        BinanceTestnetAdapter(KEY, SECRET, base_url=url)


@pytest.mark.parametrize("url", ["https://demo-api.binance.com", "https://testnet.binance.vision"])
def test_allows_exactly_the_demo_and_testnet_hosts(url: str) -> None:
    assert url.split("//")[1] in repr(BinanceTestnetAdapter(KEY, SECRET, base_url=url))


def test_default_environment_is_demo_not_mainnet() -> None:
    assert "demo-api.binance.com" in repr(BinanceTestnetAdapter(KEY, SECRET))


def test_missing_credentials_and_repr_do_not_leak() -> None:
    with pytest.raises(ExchangeError, match="not configured"):
        BinanceTestnetAdapter("", "")
    a, _ = adapter(lambda r: httpx.Response(200, json={}))
    text = repr(a) + str(a)
    assert KEY not in text and SECRET not in text and "binance.com" in text


async def test_signed_post_sends_params_and_signature_in_the_body_not_the_url() -> None:
    a, seen = adapter(lambda r: httpx.Response(200, json=ORDER))
    await a.place_order("BTCUSDT", Side.BUY, OrderType.LIMIT, D("2.50"), "st-a", price=D("100.10"))
    req = seen[0]
    assert req.method == "POST" and req.url.path == "/api/v3/order"
    assert "signature" not in str(req.url) and req.url.query == b""  # nothing sensitive in the URL
    body = form(req)
    assert req.headers["X-MBX-APIKEY"] == KEY
    assert {"timestamp", "recvWindow", "signature"} <= set(body)
    assert body["symbol"] == "BTCUSDT" and body["type"] == "LIMIT" and body["timeInForce"] == "GTC"
    assert body["quantity"] == "2.5" and body["price"] == "100.1"  # no trailing zeros
    assert body["newClientOrderId"] == "st-a" and body["newOrderRespType"] == "RESULT"
    unsigned = "&".join(f"{k}={v}" for k, v in body.items() if k != "signature")
    from urllib.parse import urlencode

    assert body["signature"] == sign(
        SECRET, urlencode([(k, v) for k, v in body.items() if k != "signature"])
    )
    assert unsigned  # the secret itself is never transmitted
    assert SECRET not in req.content.decode() and SECRET not in str(req.headers)


async def test_signed_get_uses_the_query_and_still_signs_correctly() -> None:
    a, seen = adapter(lambda r: httpx.Response(200, json={"balances": []}))
    await a.balances()
    q = dict(seen[0].url.params)
    from urllib.parse import urlencode

    assert q["signature"] == sign(
        SECRET, urlencode([(k, v) for k, v in q.items() if k != "signature"])
    )


async def test_no_secret_key_or_signature_reaches_the_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    configure_logging("test")
    with caplog.at_level(logging.DEBUG):
        a, _ = adapter(
            lambda r: httpx.Response(
                200, json=ORDER if r.url.path == "/api/v3/order" else {"balances": []}
            )
        )
        await a.balances()
        await a.place_order("BTCUSDT", Side.BUY, OrderType.MARKET, D(1), "x")
    text = " ".join(r.getMessage() for r in caplog.records)
    assert SECRET not in text and KEY not in text and "signature=" not in text
    assert logging.getLogger("httpx").level >= logging.WARNING


# ---- orders ----


async def test_order_response_is_parsed_into_decimals_and_enums() -> None:
    a, _ = adapter(lambda r: httpx.Response(200, json=ORDER))
    o = await a.get_order("BTCUSDT", "st-a")
    assert o.status == OrderStatus.PARTIALLY_FILLED and o.type == OrderType.LIMIT
    assert o.qty == D(2) and o.executed_qty == D(1) and o.avg_price == D(100) and o.price == D(100)
    assert o.stop_price is None and o.order_list_id is None and o.exchange_order_id == "77"


async def test_stop_limit_order_carries_stop_price_and_gtc() -> None:
    a, seen = adapter(
        lambda r: httpx.Response(
            200,
            json={
                **ORDER,
                "type": "STOP_LOSS_LIMIT",
                "side": "SELL",
                "stopPrice": "98.00000000",
                "status": "NEW",
                "executedQty": "0.00000000",
                "cummulativeQuoteQty": "0.00000000",
            },
        )
    )
    o = await a.place_order(
        "BTCUSDT",
        Side.SELL,
        OrderType.STOP_LOSS_LIMIT,
        D(2),
        "st-s",
        price=D("97.8"),
        stop_price=D(98),
    )
    body = form(seen[0])
    assert body["stopPrice"] == "98" and body["price"] == "97.8" and body["timeInForce"] == "GTC"
    assert o.stop_price == D(98) and o.avg_price is None


async def test_market_order_has_no_time_in_force_or_price() -> None:
    a, seen = adapter(lambda r: httpx.Response(200, json={**ORDER, "type": "MARKET"}))
    await a.place_order("BTCUSDT", Side.BUY, OrderType.MARKET, D(1), "m")
    assert "timeInForce" not in form(seen[0]) and "price" not in form(seen[0])


async def test_oco_uses_the_new_endpoint_and_parameter_names() -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "orderListId": 5,
                "orderReports": [
                    {
                        **ORDER,
                        "clientOrderId": "o1-sl",
                        "type": "STOP_LOSS_LIMIT",
                        "side": "SELL",
                        "stopPrice": "98",
                        "status": "NEW",
                        "executedQty": "0",
                        "cummulativeQuoteQty": "0",
                    },
                    {
                        **ORDER,
                        "clientOrderId": "o1-tp",
                        "type": "LIMIT_MAKER",
                        "side": "SELL",
                        "price": "105",
                        "status": "NEW",
                        "executedQty": "0",
                        "cummulativeQuoteQty": "0",
                    },
                ],
            },
        )

    a, seen = adapter(handler)
    legs = await a.place_oco_sell("BTCUSDT", D("1.5"), D(105), D(98), D("97.8"), "o1")
    assert seen[0].url.path == "/api/v3/orderList/oco"  # not the deprecated /order/oco
    b = form(seen[0])
    assert (b["side"], b["aboveType"], b["abovePrice"]) == ("SELL", "LIMIT_MAKER", "105")
    assert (b["belowType"], b["belowStopPrice"], b["belowPrice"]) == (
        "STOP_LOSS_LIMIT",
        "98",
        "97.8",
    )
    assert b["belowTimeInForce"] == "GTC" and b["listClientOrderId"] == "o1"
    assert (b["aboveClientOrderId"], b["belowClientOrderId"]) == ("o1-tp", "o1-sl")
    assert [x.client_order_id for x in legs] == ["o1-tp", "o1-sl"]  # tp first, whatever the order
    assert legs[0].type == OrderType.LIMIT_MAKER and legs[1].type == OrderType.STOP_LOSS_LIMIT
    assert all(x.order_list_id == "5" for x in legs)


async def test_cancel_cancel_all_open_orders_and_oco_lists() -> None:
    cancelled = {**ORDER, "status": "CANCELED"}
    a, seen = adapter(lambda r: httpx.Response(200, json=cancelled))
    assert (await a.cancel_order("BTCUSDT", "st-a")).status == OrderStatus.CANCELED
    assert seen[0].method == "DELETE" and form(seen[0])["origClientOrderId"] == "st-a"

    listing = [
        cancelled,
        {
            "orderListId": 9,
            "orderReports": [
                {**cancelled, "clientOrderId": "o-tp"},
                {**cancelled, "clientOrderId": "o-sl"},
            ],
        },
    ]
    a2, _ = adapter(lambda r: httpx.Response(200, json=listing))
    out = await a2.cancel_all_orders("BTCUSDT")
    assert [o.client_order_id for o in out] == ["st-a", "o-tp", "o-sl"] and out[
        1
    ].order_list_id == "9"

    a3, _ = adapter(
        lambda r: httpx.Response(400, json={"code": -2011, "msg": "Unknown order sent."})
    )
    assert await a3.cancel_all_orders("BTCUSDT") == []  # nothing open is not an error
    a4, seen4 = adapter(lambda r: httpx.Response(200, json=[ORDER]))
    assert len(await a4.open_orders("BTCUSDT")) == 1 and seen4[0].url.params["symbol"] == "BTCUSDT"


async def test_fills_resolve_the_exchange_order_id_then_read_my_trades() -> None:
    trades = [
        {
            "id": 1,
            "price": "100.5",
            "qty": "1",
            "commission": "0.001",
            "commissionAsset": "BTC",
            "isMaker": True,
            "time": 1_750_000_000_000,
        }
    ]

    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=ORDER if req.url.path == "/api/v3/order" else trades)

    a, seen = adapter(handler)
    [f] = await a.fills("BTCUSDT", "st-a")
    assert seen[1].url.path == "/api/v3/myTrades" and seen[1].url.params["orderId"] == "77"
    assert (f.price, f.qty, f.fee, f.fee_asset, f.is_maker) == (
        D("100.5"),
        D(1),
        D("0.001"),
        "BTC",
        True,
    )


# ---- account / market ----


async def test_balances_skip_empty_assets_and_filters_parse_both_notional_forms() -> None:
    a, _ = adapter(
        lambda r: httpx.Response(
            200,
            json={
                "balances": [
                    {"asset": "USDT", "free": "100.5", "locked": "1"},
                    {"asset": "DOGE", "free": "0.0", "locked": "0.0"},
                ]
            },
        )
    )
    bal = await a.balances()
    assert set(bal) == {"USDT"} and bal["USDT"].total == D("101.5")

    info = {
        "symbols": [
            {
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01000000"},
                    {
                        "filterType": "LOT_SIZE",
                        "minQty": "0.00001000",
                        "maxQty": "9000.00000000",
                        "stepSize": "0.00001000",
                    },
                    {"filterType": "NOTIONAL", "minNotional": "5.00000000"},
                ]
            }
        ]
    }
    b, seen = adapter(lambda r: httpx.Response(200, json=info))
    f = await b.symbol_filters("BTCUSDT")
    assert (f.tick_size, f.step_size, f.min_qty, f.min_notional) == (
        D("0.01"),
        D("0.00001"),
        D("0.00001"),
        D(5),
    )
    await b.symbol_filters("BTCUSDT")
    assert len(seen) == 1  # cached

    old = {
        "symbols": [
            {
                "filters": [
                    {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                    {"filterType": "LOT_SIZE", "minQty": "1", "maxQty": "9", "stepSize": "1"},
                    {"filterType": "MIN_NOTIONAL", "minNotional": "10"},
                ]
            }
        ]
    }
    c, _ = adapter(lambda r: httpx.Response(200, json=old))
    assert (await c.symbol_filters("X")).min_notional == D(10)


async def test_last_price_and_clock_sync() -> None:
    a, _ = adapter(
        lambda r: httpx.Response(
            200,
            json={"price": "123.45"}
            if "ticker" in r.url.path
            else {"serverTime": 2_000_000_000_000},
        )
    )
    assert await a.last_price("BTCUSDT") == D("123.45")
    drift = await a.sync_time()
    assert drift < 0 and a.clock_drift_ms == drift  # local clock is behind the fake server


# ---- errors ----


@pytest.mark.parametrize(
    ("status", "body", "exc"),
    [
        (429, {}, RateLimited),
        (418, {}, IPBanned),
        (503, {}, ExchangeError),
        (400, {"code": -2013, "msg": "Order does not exist."}, UnknownOrder),
        (400, {"code": -2010, "msg": "Duplicate order sent."}, OrderRejected),
        (400, {"code": -1013, "msg": "Filter failure: NOTIONAL"}, OrderRejected),
    ],
)
async def test_http_and_api_errors_map_to_our_exceptions(
    status: int, body: dict[str, Any], exc: type[Exception]
) -> None:
    a, _ = adapter(lambda r: httpx.Response(status, json=body, headers={"retry-after": "5"}))
    with pytest.raises(exc):
        await a.get_order("BTCUSDT", "x")


async def test_duplicate_error_carries_the_code_the_order_manager_relies_on() -> None:
    a, _ = adapter(
        lambda r: httpx.Response(400, json={"code": -2010, "msg": "Duplicate order sent."})
    )
    with pytest.raises(OrderRejected, match="Duplicate") as err:
        await a.place_order("BTCUSDT", Side.BUY, OrderType.MARKET, D(1), "dup")
    assert err.value.code == -2010


async def test_non_json_response_is_an_exchange_error() -> None:
    a, _ = adapter(lambda r: httpx.Response(200, text="<html>gateway</html>"))
    with pytest.raises(ExchangeError, match="non-JSON"):
        await a.last_price("BTCUSDT")


def test_fmt_never_uses_exponents_or_trailing_zeros() -> None:
    assert fmt(D("1E+2")) == "100" and fmt(D("0.00001000")) == "0.00001" and fmt(D("2.50")) == "2.5"
    assert fmt(D(0)) == "0" and fmt(D("100")) == "100"
    json.dumps({"q": fmt(D("0.1"))})
