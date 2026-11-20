"""Trading side of the exchange boundary. Implemented by the Binance testnet adapter, the
(guarded, disabled-until-Gate-B) live adapter and the in-memory fake used in tests.

Callers reach this only through the order manager, which in turn only acts on
``RiskDecision``s: nothing else may place an order (SPEC principle 1).
"""

from abc import ABC, abstractmethod
from decimal import Decimal

from app.core.models import Side
from app.exchange.orders import Balance, Fill, OrderInfo, OrderType
from app.risk.types import SymbolFilters


class TradingAdapter(ABC):
    @abstractmethod
    async def symbol_filters(self, symbol: str) -> SymbolFilters: ...

    @abstractmethod
    async def balances(self) -> dict[str, Balance]: ...

    @abstractmethod
    async def last_price(self, symbol: str) -> Decimal: ...

    @abstractmethod
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
        """Idempotent on ``client_order_id``: re-sending the same id must not double-trade."""

    @abstractmethod
    async def place_oco_sell(
        self,
        symbol: str,
        qty: Decimal,
        tp_price: Decimal,
        stop_price: Decimal,
        stop_limit_price: Decimal,
        client_order_id: str,
    ) -> list[OrderInfo]:
        """Linked take-profit (LIMIT_MAKER) + stop (STOP_LOSS_LIMIT); one fill cancels the other.
        Returns both legs: ``<id>-tp`` and ``<id>-sl``."""

    @abstractmethod
    async def cancel_order(self, symbol: str, client_order_id: str) -> OrderInfo: ...

    @abstractmethod
    async def cancel_all_orders(self, symbol: str) -> list[OrderInfo]: ...

    @abstractmethod
    async def get_order(self, symbol: str, client_order_id: str) -> OrderInfo:
        """Raises ``UnknownOrder`` if the exchange has no such order."""

    @abstractmethod
    async def open_orders(self, symbol: str | None = None) -> list[OrderInfo]: ...

    @abstractmethod
    async def fills(self, symbol: str, client_order_id: str) -> list[Fill]: ...

    async def aclose(self) -> None:  # noqa: B027
        """Release network resources."""
