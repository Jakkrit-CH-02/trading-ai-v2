# Design: MA+RSI Filter Strategy + Multi-Symbol Backtest

**Date:** 2026-05-15  
**Branch:** bot-v2  
**Motivation:** Current MA Crossover (fast=21, slow=55) on 4h bars generates only ~2 trades per 83-day window. Goal is 4–8 high-conviction trades per month per symbol, with multi-symbol rotation multiplying that to 12–24 signals/month across a portfolio.

---

## Problem Statement

Backtesting BTCUSDT with MA Crossover (21/55, 4h, 500 bars) produced:
- Total return: 0.73% ($73.40)
- Trades: 2 (both winners)
- Period: Feb 21 – May 15, 2026

The strategy quality is good (Sharpe 2.29, 100% win rate, 0.31% drawdown) but trade frequency is far too low to compound returns meaningfully. Two levers fix this:
1. **Faster MA parameters + RSI quality gate** — more signals with a filter to prevent chasing peaks/bottoms
2. **Multi-symbol backtest** — portfolio-level opportunity surface without changing strategy logic

---

## Approach A: `ma_rsi_filter` Composite Strategy

### Signal Logic

A new strategy named `"ma_rsi_filter"` composes the existing `MACross` and `RSI` implementations.

On each bar:
1. Both `MACross` (fast EMA / slow EMA) and `RSI` are updated
2. If `MACross` emits `Buy` AND `RSI < rsi_buy_max` → emit **Buy**
3. If `MACross` emits `Sell` AND `RSI > rsi_sell_min` → emit **Sell**
4. Otherwise → emit **Hold** with reason `"rsi_gate_blocked"` (if MA fired) or `"no_cross"`

Rationale for thresholds:
- `rsi_buy_max=60`: prevents buying when the market is already overbought (RSI≥60 means price has run significantly — entering here often means buying a top)
- `rsi_sell_min=40`: prevents selling when the market is oversold (RSI≤40 means price has already dropped — shorting here often means selling a bottom)

### Default Parameters

| Param | Default | Range | Meaning |
|---|---|---|---|
| `fast` | 9 | 2–50 | Fast EMA period |
| `slow` | 21 | 5–200 | Slow EMA period |
| `rsi_period` | 14 | 2–50 | RSI lookback |
| `rsi_buy_max` | 60 | 50–80 | Max RSI to allow buy entry |
| `rsi_sell_min` | 40 | 20–50 | Min RSI to allow sell entry |

### Files Changed (Backend)

- **New:** `apps/backend/internal/strategy/builtin/ma_rsi_filter.go`
  - `MARSIFilter` struct holding `*MACross` and `*RSI`
  - `Name() string` returns `"ma_rsi_filter"`
  - `OnBar()` implements composite logic above
  - `MARSIFilterFactory()` reads params with defaults, constructs both sub-strategies
- **Edit:** `apps/backend/internal/strategy/registry.go`
  - Register `"ma_rsi_filter"` → `MARSIFilterFactory`

### Expected Impact

With fast=9/slow=21 on 4h BTCUSDT: ~6–10 MA crossovers per 83-day window. RSI gate blocks ~20–30% of those at extremes → **4–8 high-conviction entries/month**.

---

## Approach C: Multi-Symbol Backtest

### API

**New endpoint:** `POST /api/backtest/multi`

Request body:
```json
{
  "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT"],
  "interval": "4h",
  "strategy_name": "ma_rsi_filter",
  "strategy_params": { "fast": "9", "slow": "21" },
  "initial_cash": "10000",
  "position_fraction": "0.1",
  "stop_loss_pct": "0.08",
  "trail_activation_pct": "0.03",
  "trail_pct": "0.02",
  "from_ms": 0,
  "to_ms": 0,
  "limit": 500
}
```

Response:
```json
{
  "results": [ <backtest.Result>, ... ]
}
```

Constraints:
- Max 10 symbols; return 400 if exceeded
- Runs sequentially (one `Engine` per symbol); no goroutine fan-out in v1 to keep complexity low
- Each symbol gets an independent `Engine` and `risk.Engine` instance — no shared state
- The existing `POST /api/backtest/run` endpoint is unchanged

### Files Changed (Backend)

- **Edit:** `apps/backend/internal/backtest/handler.go`
  - Add `MultiRunHandler` func
  - Parse `symbols []string`, validate len ≤ 10
  - Loop: build `Config{Symbol: sym, ...}`, construct engine, call `engine.Run(ctx, bars)`
  - Collect results, return JSON
- **Edit:** `apps/backend/internal/backtest/router.go`
  - Register `POST /multi` → `MultiRunHandler`

### Frontend: Symbol Multi-Select

**File:** `apps/frontend/src/pages/backtest/BacktestRunForm.tsx`

- Replace `<TextField label="Symbol">` with `<Autocomplete multiple freeSolo>` (MUI)
- Preset options: `["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"]`
- User can type any symbol and press Enter to add it
- Value stored as `string[]` in form state

**Submission routing** (in `BacktestPage` or the submit handler):
- `symbols.length === 1` → call existing `POST /api/backtest/run` (backwards-compat)
- `symbols.length > 1` → call new `POST /api/backtest/multi`

### Frontend: Multi-Symbol Results Display

**File:** `apps/frontend/src/pages/backtest/BacktestPage.tsx` (or wherever results are rendered)

When `results` is an array with length > 1:
1. **Comparison table** (top): one row per symbol — Symbol, Total Return, Win Rate, Sharpe, Max Drawdown, Trades. Sortable by any column.
2. **Per-symbol accordion panels** (below): each collapsed by default. Expanding shows the existing equity curve + trade table for that symbol. Header shows symbol + total return as a quick label.

Single-symbol results render exactly as before (no regression).

### Files Changed (Frontend)

- `apps/frontend/src/api/backtest.ts` — add `RunMultiBacktestInput`, `MultiBacktestResult` types; add `runMultiBacktest()` function
- `apps/frontend/src/pages/backtest/BacktestRunForm.tsx` — symbol multi-select + RSI param fields for `ma_rsi_filter`
- `apps/frontend/src/pages/backtest/BacktestPage.tsx` — route to multi endpoint; render comparison table + accordions

---

## RSI Param Fields in Form

When strategy is `"ma_rsi_filter"`, the form shows three additional fields (conditionally rendered, same pattern as existing fast/slow period fields):

| Field label | Form key | Default |
|---|---|---|
| RSI Period | `rsi_period` | 14 |
| RSI Buy Max (0..100) | `rsi_buy_max` | 60 |
| RSI Sell Min (0..100) | `rsi_sell_min` | 40 |

---

## Out of Scope

- Paper and live trading multi-symbol support (Phase 2)
- Parallel execution of multi-symbol backtests (Phase 2 — sequential is sufficient for UI responsiveness at ≤10 symbols)
- Parameter optimization / grid search (separate feature)
- AI strategy improvements (separate feature)
