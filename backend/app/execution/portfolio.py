"""Portfolio state from exchange balances: the same construction for manual orders (API) and
bot orders (runner), so the Risk Engine always sees the account the same way."""

from collections.abc import Mapping
from decimal import Decimal

from app.exchange.orders import Balance
from app.execution.store import ExecutionStore
from app.risk.types import PortfolioState, PositionView

ZERO = Decimal(0)
DUST_USDT = Decimal(10)  # holdings below this do not count as a position


async def build_portfolio(
    balances: Mapping[str, Balance],
    prices: Mapping[str, Decimal],
    store: ExecutionStore,
    day_start: Decimal | None = None,
    week_start: Decimal | None = None,
    peak: Decimal | None = None,
    quote: str = "USDT",
) -> PortfolioState:
    """``prices`` maps symbol -> last price (``BTCUSDT``). Anything held without a recorded,
    protected position is treated as having no stop (worst case)."""
    usdt = balances.get(quote)
    cash = usdt.free if usdt else ZERO
    equity = cash + (usdt.locked if usdt else ZERO)
    held: list[PositionView] = []
    for asset, b in balances.items():
        symbol = f"{asset}{quote}"
        if asset == quote or b.total <= 0 or symbol not in prices:
            continue
        px = prices[symbol]
        equity += b.total * px
        stop = None
        pos = await store.get_position(symbol)
        if pos is not None and pos.protected:
            stop = pos.stop
        if b.total * px >= DUST_USDT:
            held.append(PositionView(symbol, b.total, px, px, stop))
    day = day_start or equity
    return PortfolioState(
        equity,
        cash,
        max(equity, peak or equity, day),
        day,
        week_start or day,
        tuple(held),
    )
