from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from app.core.models import BotStatus, Side
from app.risk import (
    CircuitBreakers,
    MarketState,
    PortfolioState,
    PositionView,
    RiskEngine,
    RiskProfile,
    SymbolFilters,
    TradeIntent,
)

D = Decimal
NOW = datetime(2025, 6, 11, 12, 0, tzinfo=UTC)  # a Wednesday
FILTERS = SymbolFilters(
    tick_size=D("0.01"),
    step_size=D("0.00001"),
    min_qty=D("0.00001"),
    max_qty=D(9000),
    min_notional=D(10),
)


def make_engine(now: datetime = NOW, **profile_kw: Any) -> RiskEngine:
    engine = RiskEngine(RiskProfile(**profile_kw))
    engine.breakers.record_tick(now)  # fail-safe: no tick ever seen == stale
    return engine


def make_portfolio(
    equity: Any = 10_000,
    cash: Any | None = None,
    positions: tuple[PositionView, ...] = (),
    peak: Any | None = None,
    day_start: Any | None = None,
    week_start: Any | None = None,
) -> PortfolioState:
    eq = D(str(equity))
    return PortfolioState(
        equity=eq,
        cash=D(str(cash)) if cash is not None else eq - sum((p.notional for p in positions), D(0)),
        peak_equity=D(str(peak)) if peak is not None else eq,
        day_start_equity=D(str(day_start)) if day_start is not None else eq,
        week_start_equity=D(str(week_start)) if week_start is not None else eq,
        positions=positions,
    )


def make_market(**kw: Any) -> MarketState:
    base: dict[str, Any] = {
        "now": NOW,
        "bot_status": BotStatus.RUNNING,
        "data_age_s": 1.0,
        "clock_drift_ms": 50.0,
    }
    base.update(kw)
    return MarketState(**base)


def make_intent(**kw: Any) -> TradeIntent:
    base: dict[str, Any] = {
        "symbol": "BTCUSDT",
        "side": Side.BUY,
        "entry": D(100),
        "stop": D(98),
        "tp1": D(105),
        "strategy": "s1",
    }
    base.update(kw)
    return TradeIntent(**base)


def position(symbol: str, notional: Any, stop_pct: Any = "0.02", price: Any = 100) -> PositionView:
    """A position worth ``notional`` with its stop ``stop_pct`` below the mark."""
    px = D(str(price))
    qty = D(str(notional)) / px
    return PositionView(symbol, qty, px, px, px * (1 - D(str(stop_pct))))


def breakers(engine: RiskEngine) -> CircuitBreakers:
    return engine.breakers
