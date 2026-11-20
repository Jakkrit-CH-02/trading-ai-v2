from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.core.models import Side
from app.exchange.fake import FakeTradingExchange
from app.exchange.orders import OrderInfo, OrderType
from app.execution import ExecConfig, InMemoryExecutionStore, OrderManager
from app.risk import RiskEngine
from tests.risk_helpers import FILTERS, NOW, make_engine, make_intent, make_market, make_portfolio

D = Decimal
BOT = "01ARZ3NDEKTSV4RRFFQ69G5FAV"  # a real-looking ULID: 26 chars
SIG = "01BX5ZZKBKACTAV9WEVGEMMVRY"


@dataclass
class Clock:
    """Virtual monotonic clock: ``sleep`` advances time instantly and runs hooks, so
    entry-timeout and polling logic is testable without waiting."""

    t: float = 0.0
    hooks: list[Callable[[float], None]] = field(default_factory=list)

    def mono(self) -> float:
        return self.t

    async def sleep(self, d: float) -> None:
        self.t += d
        for h in list(self.hooks):
            h(self.t)


@dataclass
class Env:
    ex: FakeTradingExchange
    store: InMemoryExecutionStore
    mgr: OrderManager
    risk: RiskEngine
    clock: Clock

    async def submit(self, **intent_kw: Any) -> Any:
        intent_kw.setdefault("bot_id", BOT)
        intent_kw.setdefault("signal_id", SIG)
        return await self.mgr.submit(make_intent(**intent_kw), self.portfolio(), make_market())

    def portfolio(self) -> Any:
        return make_portfolio(equity=10_000, cash=10_000)

    def open_order_types(self) -> list[str]:
        return sorted(
            f"{o.type.value}:{o.side.value}" for o in self.ex.orders.values() if o.status.is_open
        )


def make_env(
    price: str = "100",
    fee_in_base: bool = False,
    use_virtual_monotonic: bool = True,
    **cfg: Any,
) -> Env:
    ex = FakeTradingExchange(
        {"BTCUSDT": D(price)}, free={"USDT": D(10_000)}, filters=FILTERS, fee_in_base=fee_in_base
    )
    ex.now = NOW
    clock = Clock()
    risk = make_engine()
    store = InMemoryExecutionStore()
    config = ExecConfig(**{"entry_timeout_s": 5.0, "poll_interval_s": 1.0, **cfg})
    kw: dict[str, Any] = {}
    if use_virtual_monotonic:
        kw = {"monotonic": clock.mono, "sleep": clock.sleep}
    mgr = OrderManager(ex, risk, store, config, now=lambda: NOW, **kw)
    return Env(ex, store, mgr, risk, clock)


class LostResponseExchange(FakeTradingExchange):
    """The order reaches the exchange but the HTTP response is lost (timeout)."""

    lose_next_response = True

    async def place_order(self, *a: Any, **k: Any) -> OrderInfo:
        info = await super().place_order(*a, **k)
        if self.lose_next_response and info.type != OrderType.STOP_LOSS_LIMIT:
            self.lose_next_response = False
            from app.exchange.errors import ExchangeError

            raise ExchangeError("read timeout")
        return info


__all__ = ["BOT", "SIG", "Clock", "Env", "LostResponseExchange", "Side", "make_env"]
