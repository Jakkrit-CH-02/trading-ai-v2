"""Backtest <-> Risk Engine bridge. The backtester sizes and approves entries with the very
same ``RiskEngine`` (and circuit breakers) that the order manager uses, so a backtest can no
longer take trades live would refuse (SPEC principle 2)."""

from datetime import datetime
from decimal import Decimal

from app.core.models import BotStatus, Side
from app.risk import (
    MarketState,
    PortfolioState,
    RiskDecision,
    RiskEngine,
    RiskProfile,
    SymbolFilters,
    TradeIntent,
)
from app.strategies.types import Signal

QTY_STEP = Decimal("0.00000001")


class RiskGate:
    def __init__(
        self,
        risk_per_trade: Decimal,
        fee_rate: Decimal,
        slippage_rate: Decimal,
        max_symbol_exposure: Decimal,
        min_notional: Decimal,
        initial_equity: Decimal,
    ) -> None:
        self.engine = RiskEngine(
            RiskProfile(
                risk_per_trade=risk_per_trade,
                fee_rate=fee_rate,
                slippage_rate=slippage_rate,
                max_symbol_exposure=max_symbol_exposure,
            )
        )
        # permissive exchange filters: a backtest has no per-symbol tick/step data
        self.filters = SymbolFilters(
            Decimal("0.00000001"), QTY_STEP, QTY_STEP, Decimal(10**12), min_notional
        )
        self.peak = self.day_start = self.week_start = initial_equity
        self._day: object = None
        self._week: object = None

    def on_bar_close(self, close_time: datetime, equity: Decimal) -> None:
        """Feed time and equity: tick freshness, peak, and day/week baselines for the breakers."""
        self.engine.breakers.record_tick(close_time)
        self.peak = max(self.peak, equity)
        day, week = close_time.date(), close_time.isocalendar()[:2]
        if day != self._day:
            self._day, self.day_start = day, equity
        if week != self._week:
            self._week, self.week_start = week, equity

    def decide(
        self,
        now: datetime,
        cash: Decimal,
        symbol: str,
        fill: Decimal,
        sig: Signal,
        size_factor: Decimal,
    ) -> RiskDecision:
        portfolio = PortfolioState(cash, cash, self.peak, self.day_start, self.week_start)
        market = MarketState(now, BotStatus.RUNNING, 0.0, 0.0)
        intent = TradeIntent(
            symbol=symbol,
            side=Side.BUY,
            entry=fill,
            stop=sig.stop,
            strategy=sig.strategy,
            tp1=sig.tp1,
            size_factor=size_factor,
        )
        return self.engine.evaluate(intent, portfolio, market, self.filters)

    def record_trade(self, pnl: Decimal) -> None:
        self.engine.breakers.record_trade_result(pnl)

    @property
    def kill_switch_active(self) -> bool:
        return self.engine.breakers.kill_switch_active
