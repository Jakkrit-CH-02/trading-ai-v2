import json
from datetime import UTC, datetime
from decimal import Decimal

import httpx
import pytest

from app.exchange.binance_public import BinancePublicAdapter, parse_rest_kline, parse_ws_message
from app.exchange.errors import ExchangeError, IPBanned, RateLimited
from app.exchange.ratelimit import WeightTracker
from app.exchange.types import BookTicker, Kline

# Row layout from the Binance spot klines docs.
ROW = [1735689600000, "93500.10", "93800.00", "93400.00", "93650.55", "12.5",
       1735693199999, "1170000.5", 321, "6.2", "580000.1", "0"]  # fmt: skip


def test_parse_rest_kline_uses_decimal_and_utc() -> None:
    k = parse_rest_kline("BTCUSDT", "1h", ROW, now_ms=1735693200000)
    assert k.open_time == datetime(2025, 1, 1, tzinfo=UTC)
    assert k.o == Decimal("93500.10") and isinstance(k.c, Decimal)
    assert k.trades == 321 and k.is_closed


def test_rest_kline_still_forming_is_not_closed() -> None:
    assert not parse_rest_kline("BTCUSDT", "1h", ROW, now_ms=1735690000000).is_closed


def test_parse_ws_kline_frame() -> None:
    frame = {
        "stream": "btcusdt@kline_1h",
        "data": {
            "e": "kline",
            "k": {"t": 1735689600000, "T": 1735693199999, "s": "BTCUSDT", "i": "1h",
                  "o": "1.0", "c": "2.0", "h": "3.0", "l": "0.5", "v": "9", "n": 7,
                  "x": True, "q": "18", "V": "4"},
        },
    }  # fmt: skip
    k = parse_ws_message(json.dumps(frame))
    assert isinstance(k, Kline) and k.is_closed and k.c == Decimal("2.0") and k.interval == "1h"


def test_parse_ws_book_ticker_frame() -> None:
    data = {"u": 1, "s": "BTCUSDT", "b": "100.1", "B": "2", "a": "100.2", "A": "3"}
    frame = {"stream": "btcusdt@bookTicker", "data": data}
    t = parse_ws_message(json.dumps(frame))
    assert isinstance(t, BookTicker) and t.ask == Decimal("100.2")


def test_parse_ws_ignores_unknown_frames() -> None:
    assert parse_ws_message(json.dumps({"result": None, "id": 1})) is None


def _adapter(handler: httpx.MockTransport, **kw: object) -> BinancePublicAdapter:
    return BinancePublicAdapter(client=httpx.AsyncClient(transport=handler), **kw)  # type: ignore[arg-type]


async def test_get_klines_drops_the_forming_candle() -> None:
    closed = ROW
    forming = [1735693200000, "1", "1", "1", "1", "1", 1735696799999, "1", 1, "1", "1", "0"]

    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == "/api/v3/time":
            return httpx.Response(200, json={"serverTime": 1735693500000})
        return httpx.Response(200, json=[closed, forming])

    klines = await _adapter(httpx.MockTransport(handler)).get_klines("BTCUSDT", "1h")
    assert [k.open_time.timestamp() * 1000 for k in klines] == [1735689600000]


@pytest.mark.parametrize(
    ("status", "exc"), [(429, RateLimited), (418, IPBanned), (500, ExchangeError)]
)
async def test_http_errors_map_to_exceptions(status: int, exc: type[Exception]) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, headers={"retry-after": "30"}, text="nope")

    with pytest.raises(exc):
        await _adapter(httpx.MockTransport(handler)).server_time()


async def test_used_weight_header_triggers_throttle() -> None:
    sleeps: list[float] = []

    async def fake_sleep(s: float) -> None:
        sleeps.append(s)

    weights = WeightTracker(limit=6000, sleep=fake_sleep, clock=lambda: 30.0)

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"x-mbx-used-weight-1m": "4900"}, json={"serverTime": 1735693500000}
        )

    adapter = _adapter(httpx.MockTransport(handler), weights=weights)
    await adapter.server_time()  # records 4900 / 6000 = 81.7% >= 80%
    assert weights.should_throttle and not sleeps
    await adapter.server_time()  # next call must wait for the minute to roll over
    assert sleeps == [pytest.approx(30.5)] and weights.used == 4900  # header refreshed after
