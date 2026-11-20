"""S4 Bounded Grid (SPEC 2.2, Spot): RANGE regime only.

Unlike S1-S3 a grid holds many small positions at once, so it is a *plan* (``GridPlan``)
rather than a single ``Signal``. ``plan_grid`` is pure: given features up to bar ``i`` it
returns the price levels or ``None``. Fills, the stop and the regime exit are simulated by
``backtest/grid.py`` and, in live, driven by the execution layer (Phase 3).

Grid rules implemented:
- 10-20 levels between support (lowest low) and resistance (highest high) of the lookback,
  using the largest level count whose spacing is >= 3x the round-trip fee.
- Buy at each level below the current price, sell one level above.
- Stop the whole grid and close everything if price closes more than 1 ATR below the
  lower bound, or the regime leaves RANGE.
"""

from dataclasses import dataclass
from decimal import Decimal

import numpy as np

from app.marketdata import indicators as ind
from app.strategies.base import (
    MarketFrames,
    base_columns,
    is_nan,
    regime_columns,
    to_features,
)
from app.strategies.features import Features, dec
from app.strategies.params import S4Params
from app.strategies.types import Regime


@dataclass(frozen=True, slots=True)
class GridPlan:
    symbol: str
    bar_time: object  # open_time of the bar the plan was made on
    levels: tuple[Decimal, ...]  # ascending; levels[k] is bought, levels[k+1] is its sell
    lower: Decimal
    upper: Decimal
    stop: Decimal  # lower - stop_atr * ATR
    atr: Decimal


class S4Grid:
    name = "s4"
    exec_interval = "1h"

    def __init__(self, params: S4Params | None = None) -> None:
        self.p = params or S4Params()

    def prepare(self, data: MarketFrames) -> Features:
        p, df = self.p, data.frames["1h"]
        high, low, close = df["high"], df["low"], df["close"]
        cols = base_columns(df, "1h")
        cols.update(
            atr=ind.atr(high, low, close, p.atr_period),
            # support / resistance of the *previous* `lookback` bars (excludes bar i)
            support=low.rolling(p.lookback, min_periods=p.lookback).min().shift(1),
            resistance=high.rolling(p.lookback, min_periods=p.lookback).max().shift(1),
        )
        cols.update(regime_columns(data, df.index, "1h", p.regime))
        return to_features(data.symbol, "1h", cols)

    def in_range_regime(self, f: Features, i: int) -> bool:
        return bool(f["regime4"][i] in self.p.regimes) and f["btc_regime"][i] != Regime.TREND_DOWN

    def plan_grid(self, f: Features, i: int, round_trip_fee: float) -> GridPlan | None:
        """Decide at the close of bar ``i`` whether to start a grid (uses ``<= i`` only)."""
        p = self.p
        if not self.in_range_regime(f, i):
            return None
        lower, upper, atr, price = f["support"][i], f["resistance"][i], f["atr"][i], f["close"][i]
        if is_nan(lower, upper, atr, price) or not (lower < price < upper):
            return None
        min_spacing = p.min_spacing_fee_mult * round_trip_fee * price
        for n in range(p.max_levels, p.min_levels - 1, -1):
            if (upper - lower) / (n - 1) >= min_spacing:
                levels = tuple(dec(x) for x in np.linspace(lower, upper, n))
                return GridPlan(
                    symbol=f.symbol,
                    bar_time=f.time(i),
                    levels=levels,
                    lower=dec(lower),
                    upper=dec(upper),
                    stop=dec(lower - p.stop_atr * atr),
                    atr=dec(atr),
                )
        return None  # range too tight to pay for the fees
