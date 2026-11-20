"""Binance **Spot Demo / Testnet** trading adapter (HMAC-signed REST, fake money only).

Safety rails, enforced here rather than in documentation:
- The base URL host must be exactly ``demo-api.binance.com`` (Demo Mode) or
  ``testnet.binance.vision``; anything else raises ``LiveTradingForbidden`` (live trading is
  not allowed before Gate B, SPEC 13). A mainnet key cannot be used through this class: those
  environments would reject it and no other host is reachable.
- The API key and secret are held privately, never logged, and never appear in ``repr``.
- Signed parameters travel in the request *body* for POST/DELETE, so a signature never
  appears in a URL; GET requests (which must carry them in the query) rely on the httpx
  logger being silenced in ``configure_logging``.
"""

import hashlib
import hmac
import time
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode, urlparse

import httpx
import structlog

from app.core.models import Side
from app.exchange.errors import (
    ExchangeError,
    IPBanned,
    LiveTradingForbidden,
    OrderRejected,
    RateLimited,
    UnknownOrder,
)
from app.exchange.orders import Balance, Fill, OrderInfo, OrderStatus, OrderType
from app.exchange.ratelimit import WeightTracker
from app.exchange.trading import TradingAdapter
from app.exchange.types import ms_to_dt
from app.risk.types import SymbolFilters

log = structlog.get_logger()

TESTNET_HOST = "testnet.binance.vision"
DEMO_HOST = "demo-api.binance.com"  # Binance Demo Mode for Spot (launched 2026-01-29)
TESTNET_URL = f"https://{TESTNET_HOST}"
DEMO_URL = f"https://{DEMO_HOST}"
# The only hosts this adapter may ever talk to. Both trade with fake money. Real Binance
# (api.binance.com and friends) is deliberately absent: live trading is not allowed before Gate B.
ALLOWED_HOSTS = frozenset({TESTNET_HOST, DEMO_HOST})
ENVIRONMENTS = {"demo": DEMO_URL, "testnet": TESTNET_URL}


def sign(secret: str, query: str) -> str:
    return hmac.new(secret.encode(), query.encode(), hashlib.sha256).hexdigest()


def fmt(d: Decimal) -> str:
    """Plain decimal string without exponent or trailing zeros (what the API expects)."""
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _dec(v: Any) -> Decimal:
    return Decimal(str(v))


class BinanceTestnetAdapter(TradingAdapter):
    def __init__(
        self,
        api_key: str,
        api_secret: str,
        base_url: str = DEMO_URL,
        client: httpx.AsyncClient | None = None,
        recv_window: int = 5000,
        weights: WeightTracker | None = None,
    ) -> None:
        host = urlparse(base_url).hostname
        if urlparse(base_url).scheme != "https" or host not in ALLOWED_HOSTS:
            raise LiveTradingForbidden(
                f"refusing to trade against {host!r}: only {sorted(ALLOWED_HOSTS)} are allowed "
                "before Gate B"
            )
        if not api_key or not api_secret:
            raise ExchangeError("testnet API key/secret are not configured")
        self.__key, self.__secret = api_key, api_secret
        self._base = base_url.rstrip("/")
        self._client = client or httpx.AsyncClient(timeout=10.0)
        self._owns_client = client is None
        self._recv = recv_window
        self.weights = weights or WeightTracker()
        self._offset_ms = 0
        self._filters: dict[str, SymbolFilters] = {}

    def __repr__(self) -> str:  # never reveal credentials
        return f"BinanceTestnetAdapter(base={self._base!r})"

    # ---- transport --------------------------------------------------------------------------

    @property
    def clock_drift_ms(self) -> float:
        """Local clock minus exchange clock, as measured by the last ``sync_time``."""
        return float(-self._offset_ms)

    async def sync_time(self) -> float:
        """Measure the offset to Binance's clock (SPEC 8.3: every 10 minutes)."""
        t0 = int(time.time() * 1000)
        res = await self._client.get(f"{self._base}/api/v3/time")
        t1 = int(time.time() * 1000)
        server = int(res.json()["serverTime"])
        self._offset_ms = server - (t0 + t1) // 2
        return self.clock_drift_ms

    async def _request(
        self, method: str, path: str, params: dict[str, Any] | None = None, signed: bool = False
    ) -> Any:
        await self.weights.wait_if_needed()
        p = {k: v for k, v in (params or {}).items() if v is not None}
        headers = {"X-MBX-APIKEY": self.__key}
        data: dict[str, str] | None = None
        query: dict[str, str] | None = None
        if signed:
            p["recvWindow"] = self._recv
            p["timestamp"] = int(time.time() * 1000) + self._offset_ms
            body = urlencode(p)
            p["signature"] = sign(self.__secret, body)
            if method == "GET":
                query = {k: str(v) for k, v in p.items()}
            else:
                data = {k: str(v) for k, v in p.items()}  # body, not URL
        else:
            query = {k: str(v) for k, v in p.items()}
        res = await self._client.request(
            method, f"{self._base}{path}", params=query, data=data, headers=headers
        )
        self.weights.update_from_headers(res.headers)
        return self._handle(res, path)

    @staticmethod
    def _handle(res: httpx.Response, path: str) -> Any:
        retry_after = float(res.headers.get("retry-after", "60"))
        if res.status_code == 418:
            raise IPBanned(retry_after)
        if res.status_code == 429:
            raise RateLimited(retry_after)
        if res.status_code >= 500:
            raise ExchangeError(f"{path}: server error {res.status_code}")
        try:
            body = res.json()
        except ValueError as e:
            raise ExchangeError(f"{path}: non-JSON response {res.status_code}") from e
        if res.status_code >= 400:
            code, msg = body.get("code"), body.get("msg", "")
            if code == -2013:  # "Order does not exist."
                raise UnknownOrder(msg)
            raise OrderRejected(msg or f"{path} rejected", code)
        return body

    # ---- parsing ------------------------------------------------------------------------------

    @staticmethod
    def _order(o: dict[str, Any]) -> OrderInfo:
        executed = _dec(o.get("executedQty", "0"))
        quote = _dec(o.get("cummulativeQuoteQty", "0"))
        otype = OrderType(o["type"])
        price = _dec(o["price"]) if o.get("price") not in (None, "0.00000000") else None
        stop = _dec(o["stopPrice"]) if o.get("stopPrice") not in (None, "0.00000000") else None
        ts = o.get("updateTime") or o.get("transactTime") or o.get("time")
        return OrderInfo(
            client_order_id=o["clientOrderId"],
            symbol=o["symbol"],
            side=Side(o["side"]),
            type=otype,
            status=OrderStatus(o["status"]),
            qty=_dec(o["origQty"]),
            executed_qty=executed,
            price=price,
            stop_price=stop,
            avg_price=(quote / executed) if executed else None,
            exchange_order_id=str(o.get("orderId")) if o.get("orderId") is not None else None,
            order_list_id=str(o["orderListId"]) if o.get("orderListId", -1) != -1 else None,
            ts=ms_to_dt(int(ts)) if ts else None,
        )

    # ---- TradingAdapter -----------------------------------------------------------------------

    async def symbol_filters(self, symbol: str) -> SymbolFilters:
        if symbol not in self._filters:
            info = await self._request("GET", "/api/v3/exchangeInfo", {"symbol": symbol})
            by_type = {f["filterType"]: f for f in info["symbols"][0]["filters"]}
            lot, price = by_type["LOT_SIZE"], by_type["PRICE_FILTER"]
            notional = by_type.get("NOTIONAL") or by_type.get("MIN_NOTIONAL") or {}
            self._filters[symbol] = SymbolFilters(
                tick_size=_dec(price["tickSize"]),
                step_size=_dec(lot["stepSize"]),
                min_qty=_dec(lot["minQty"]),
                max_qty=_dec(lot["maxQty"]),
                min_notional=_dec(notional.get("minNotional", "0")),
            )
        return self._filters[symbol]

    async def account_info(self) -> dict[str, Any]:
        """Raw signed ``GET /api/v3/account`` (canTrade / canWithdraw / permissions)."""
        res: dict[str, Any] = await self._request("GET", "/api/v3/account", signed=True)
        return res

    async def balances(self) -> dict[str, Balance]:
        acct = await self._request("GET", "/api/v3/account", signed=True)
        return {
            b["asset"]: Balance(b["asset"], _dec(b["free"]), _dec(b["locked"]))
            for b in acct["balances"]
            if _dec(b["free"]) or _dec(b["locked"])
        }

    async def last_price(self, symbol: str) -> Decimal:
        res = await self._request("GET", "/api/v3/ticker/price", {"symbol": symbol})
        return _dec(res["price"])

    async def place_order(
        self,
        symbol: str,
        side: Side,
        type: OrderType,
        qty: Decimal,
        client_order_id: str,
        price: Decimal | None = None,
        stop_price: Decimal | None = None,
    ) -> OrderInfo:
        params: dict[str, Any] = {
            "symbol": symbol,
            "side": side.value,
            "type": type.value,
            "quantity": fmt(qty),
            "newClientOrderId": client_order_id,
            "newOrderRespType": "RESULT",
        }
        if type in (OrderType.LIMIT, OrderType.STOP_LOSS_LIMIT):
            params["timeInForce"] = "GTC"
        if price is not None:
            params["price"] = fmt(price)
        if stop_price is not None:
            params["stopPrice"] = fmt(stop_price)
        return self._order(await self._request("POST", "/api/v3/order", params, signed=True))

    async def place_oco_sell(
        self,
        symbol: str,
        qty: Decimal,
        tp_price: Decimal,
        stop_price: Decimal,
        stop_limit_price: Decimal,
        client_order_id: str,
    ) -> list[OrderInfo]:
        """``POST /api/v3/orderList/oco`` (the old ``/order/oco`` is deprecated)."""
        tp_id, sl_id = f"{client_order_id}-tp", f"{client_order_id}-sl"
        res = await self._request(
            "POST",
            "/api/v3/orderList/oco",
            {
                "symbol": symbol,
                "side": "SELL",
                "quantity": fmt(qty),
                "listClientOrderId": client_order_id,
                "aboveType": "LIMIT_MAKER",
                "abovePrice": fmt(tp_price),
                "aboveClientOrderId": tp_id,
                "belowType": "STOP_LOSS_LIMIT",
                "belowStopPrice": fmt(stop_price),
                "belowPrice": fmt(stop_limit_price),
                "belowTimeInForce": "GTC",
                "belowClientOrderId": sl_id,
                "newOrderRespType": "RESULT",
            },
            signed=True,
        )
        by_id = {r["clientOrderId"]: r for r in res["orderReports"]}
        legs = []
        for cid in (tp_id, sl_id):
            r = {**by_id[cid], "orderListId": res.get("orderListId", -1)}
            legs.append(self._order(r))
        return legs

    async def cancel_order(self, symbol: str, client_order_id: str) -> OrderInfo:
        res = await self._request(
            "DELETE",
            "/api/v3/order",
            {"symbol": symbol, "origClientOrderId": client_order_id},
            signed=True,
        )
        return self._order(res)

    async def cancel_all_orders(self, symbol: str) -> list[OrderInfo]:
        try:
            res = await self._request(
                "DELETE", "/api/v3/openOrders", {"symbol": symbol}, signed=True
            )
        except OrderRejected as e:
            if e.code == -2011:  # nothing to cancel
                return []
            raise
        out: list[OrderInfo] = []
        for item in res:
            if "orderReports" in item:  # an OCO list
                out += [
                    self._order({**r, "orderListId": item.get("orderListId", -1)})
                    for r in item["orderReports"]
                ]
            else:
                out.append(self._order(item))
        return out

    async def get_order(self, symbol: str, client_order_id: str) -> OrderInfo:
        res = await self._request(
            "GET",
            "/api/v3/order",
            {"symbol": symbol, "origClientOrderId": client_order_id},
            signed=True,
        )
        return self._order(res)

    async def open_orders(self, symbol: str | None = None) -> list[OrderInfo]:
        res = await self._request("GET", "/api/v3/openOrders", {"symbol": symbol}, signed=True)
        return [self._order(o) for o in res]

    async def fills(self, symbol: str, client_order_id: str) -> list[Fill]:
        order = await self.get_order(symbol, client_order_id)
        if not order.exchange_order_id:
            return []
        res = await self._request(
            "GET",
            "/api/v3/myTrades",
            {"symbol": symbol, "orderId": order.exchange_order_id},
            signed=True,
        )
        return [
            Fill(
                client_order_id=client_order_id,
                symbol=symbol,
                trade_id=str(t["id"]),
                price=_dec(t["price"]),
                qty=_dec(t["qty"]),
                fee=_dec(t["commission"]),
                fee_asset=t["commissionAsset"],
                is_maker=bool(t["isMaker"]),
                ts=ms_to_dt(int(t["time"])),
            )
            for t in res
        ]

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()
