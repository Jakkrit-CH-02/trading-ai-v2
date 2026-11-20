"""Grid backtest for S4. Conservative bar-level simulation:

- A level buys when the bar's low trades through it; the matching sell is one level up and
  fills when the high reaches it. Within one bar, sells for inventory held from *earlier*
  bars are processed before new buys, so a buy and its own sell never complete in the same
  bar (the intrabar order is unknowable from OHLC).
- Limit fills happen at the level price with the taker fee (conservative: no maker rebate)
  and no slippage. Forced exits (stop / regime change) are market orders with slippage.
- Capital: ``allocation`` x equity is split equally across the buy levels.
- Stop: close below ``lower - 1 x ATR`` or the 4H regime leaving RANGE closes everything at
  that bar's close. Exchange-side protection is Phase 3.
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

import pandas as pd

from app.backtest.engine import QTY_STEP, BacktestConfig, BacktestResult, TradeResult
from app.strategies.features import Features, dec
from app.strategies.s4_grid import GridPlan, S4Grid


@dataclass(slots=True)
class _Lot:
    level_idx: int
    qty: Decimal
    price: Decimal
    entry_time: datetime
    idx_open: int
    fee_paid: Decimal


def run_grid_backtest(
    strategy: S4Grid,
    feats: Features,
    cfg: BacktestConfig | None = None,
    start: int = 0,
    end: int | None = None,
    initial_equity: Decimal | None = None,
) -> BacktestResult:
    cfg = cfg or BacktestConfig()
    fee, slip = cfg.fees.taker, cfg.fees.slippage
    p = strategy.p
    n = len(feats) if end is None else min(end, len(feats))
    cash = initial_equity if initial_equity is not None else cfg.initial_equity
    start_cash = cash

    grid: GridPlan | None = None
    per_level_cash = Decimal(0)
    lots: dict[int, _Lot] = {}
    trades: list[TradeResult] = []
    equity_pts: list[tuple[pd.Timestamp, float]] = []
    round_trip_fee = float(2 * fee)
    last_close = Decimal(0)
    equity_ref = start_cash  # equity at the previous bar close, for return-on-equity

    def close_lot(lot: _Lot, i: int, raw_price: Decimal, reason: str, market: bool) -> None:
        nonlocal cash
        px = raw_price * (1 - slip) if market else raw_price
        gross = lot.qty * px
        fee_leg = gross * fee
        cash += gross - fee_leg
        pnl = gross - fee_leg - (lot.qty * lot.price + lot.fee_paid)
        risk = lot.qty * (lot.price - (grid.stop if grid else lot.price))
        trades.append(
            TradeResult(
                strategy="s4",
                symbol=feats.symbol,
                entry_time=lot.entry_time,
                exit_time=feats.time(i),
                entry_price=lot.price,
                exit_price=px,
                qty=lot.qty,
                pnl=pnl,
                fees=lot.fee_paid + fee_leg,
                slippage=(lot.qty * raw_price * slip) if market else Decimal(0),
                ret_pct=float(
                    pnl / equity_ref
                ),  # on equity (not lot cost) so Monte Carlo compounds sanely
                pnl_r=float(pnl / risk) if risk > 0 else 0.0,
                bars_held=i - lot.idx_open + 1,
                exit_reason=reason,
                score=0.0,
                reasons={"level": str(lot.price)},
            )
        )

    for i in range(start, n):
        o, h, low, c = (dec(feats[k][i]) for k in ("open", "high", "low", "close"))

        if grid is not None:
            # exits that need the bar's close
            stop_hit = c < grid.stop
            regime_exit = not strategy.in_range_regime(feats, i)
            if stop_hit or regime_exit or i == n - 1:
                reason = (
                    "grid_stop" if stop_hit else ("regime_change" if regime_exit else "range_end")
                )
                for lot in list(lots.values()):
                    close_lot(lot, i, c, reason, market=True)
                lots.clear()
                grid = None
            else:
                # 1) sells for inventory carried over from earlier bars
                for k in sorted(lots):
                    lot = lots[k]
                    target = grid.levels[k + 1]
                    if lot.idx_open < i and h >= target:
                        close_lot(lot, i, target, "grid_tp", market=False)
                        del lots[k]
                # 2) buys: only levels that were resting *below* the previous close can fill
                for k in range(len(grid.levels) - 1):
                    lvl = grid.levels[k]
                    if k in lots or lvl >= last_close or low > lvl:
                        continue
                    fill = min(lvl, o)  # a gap down through the level fills at the open
                    qty = (per_level_cash / (fill * (1 + fee))).quantize(QTY_STEP, ROUND_DOWN)
                    if qty * fill < cfg.min_notional or qty * fill * (1 + fee) > cash:
                        continue
                    f_paid = qty * fill * fee
                    cash -= qty * fill + f_paid
                    lots[k] = _Lot(k, qty, fill, feats.time(i), i, f_paid)

        last_close = c
        mark = sum((lot.qty * c for lot in lots.values()), Decimal(0))
        equity_ref = cash + mark
        equity_pts.append((feats.index[i], float(equity_ref)))

        if grid is None and i < n - 1:
            plan = strategy.plan_grid(feats, i, round_trip_fee)
            if plan is not None:
                grid = plan
                n_buy = len(plan.levels) - 1
                per_level_cash = cash * Decimal(repr(p.allocation)) / n_buy

    idx = pd.DatetimeIndex([t for t, _ in equity_pts])
    return BacktestResult(
        strategy="s4",
        symbol=feats.symbol,
        trades=trades,
        signals=[],
        equity=pd.Series([v for _, v in equity_pts], index=idx, dtype="float64"),
        initial_equity=start_cash,
        final_equity=cash,
        config=cfg,
    )
