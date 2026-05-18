# Paper-mode Short Selling — Design

**Date:** 2026-05-18
**Status:** Approved, ready for implementation plan
**Scope:** Paper trading engine only. Backtest and live are out of scope.

## Problem

The system is long-only. A SELL signal closes an existing long; if no long exists, the signal is silently dropped. We can't profit from downtrends.

## Goal

A SELL signal with no existing position opens a **short**. A BUY signal with an open short **covers** it (close-only; no flip). Trailing stop, take-profit, and risk checks work symmetrically for both sides. Money handling uses `decimal.Decimal` throughout.

## Key decisions (locked)

1. Represent direction with `Position.Side domain.Side` (reuse the existing enum). `Qty` stays positive.
2. BUY while short = **cover only**. Never auto-flip to long in the same call.
3. Short cash model = **credit proceeds on open, debit on cover**. No margin reservation, no borrow/funding fees.
4. Trailing stop for shorts mirrors longs: track lowest price; SL ratchets *down* only.
5. SELL while already short = **no-op** (skip in sizer). Mirror of how BUY doesn't pyramid into longs today.

## Design

### Domain — `internal/domain/position.go`

Add two fields to `Position`:

```go
Side     domain.Side     `json:"side"`      // SideBuy = long, SideSell = short. Zero-value = long (legacy default).
TrailLow decimal.Decimal `json:"trail_low"` // lowest price since trail activated (shorts only)
```

When `Qty` returns to zero, reset `Side`, `StopLoss`, `TakeProfit`, `TrailHigh`, `TrailLow` to zero values.

### Paper engine — `internal/paper/engine.go`

#### `Place()` — branch on (order side, current position side)

| Order side | Position state | Behavior |
|---|---|---|
| BUY | empty | Open long (current behavior). `Side = SideBuy`. |
| BUY | long | Add to long. Weighted-avg entry. (current behavior) |
| BUY | short | **Cover.** `realized = (entry − fill) × qty`. `cash -= qty × fill`. If `o.Qty > pos.Qty` → `ErrInsufficientPosition`. On full cover, clear Side/SL/TP/Trail*. |
| SELL | long | Reduce long. (current behavior) |
| SELL | empty | **Open short.** `Side = SideSell`. `AvgEntry = fill`. `cash += qty × fill`. Copy SL/TP/Trail params from order. `TrailLow = fill`. |
| SELL | short | Add to short. Weighted-avg entry. `cash += qty × fill`. |

Spread unchanged: BUY fills at `mid × (1 + 1bp)`, SELL at `mid × (1 − 1bp)`.

#### Unrealized PnL & Equity

Helper:
```go
// signedQty returns +Qty for longs, -Qty for shorts.
func (p *Position) signedQty() decimal.Decimal { ... }
```

- `UnrealizedPL = (close − entry) × signedQty()` (works for both sides).
- `Equity = cash + Σ_long(qty × px) + Σ_short((entry − px) × qty)`. Short cash credit is already in `cash`; only the unrealized portion is added on top.

#### `OnBar()` — trail logic

Long branch unchanged. Add short branch:
- Activation: `price < entry × (1 − TrailActivationPct)`.
- Track `TrailLow` (lowest price seen since activation).
- New SL candidate: `TrailLow × (1 + TrailPct)`.
- SL only ratchets *down*: update only if `newSL < pos.StopLoss` (or if SL not yet set).

#### `CheckExits()` — exit conditions

Long (today): `price ≤ SL` → SL hit; `price ≥ TP` → TP hit. Exit fill at `close × (1 − bp)`. Realized = `(fill − entry) × qty`.

Short (new): `price ≥ SL` → SL hit; `price ≤ TP` (and TP > 0) → TP hit. Exit fill at `close × (1 + bp)`. Realized = `(entry − fill) × qty`. `cash -= qty × fill`. Emit event with `Side = SideBuy` (the covering action).

#### `FlattenPositions()`

Per position: send a BUY (for shorts) or SELL (for longs) at the latest close. Same `Place()` path handles accounting.

### Pipeline — `internal/runtime/pipeline.go`

`FixedFractionSizer`:

**BUY signal:**
- No position → open new long. (current behavior)
- Long open → add to long. (today's behavior is "add"; pipeline-level cooldown already gates entries, so unchanged here.)
- Short open → **cover.** Return `{Qty: pos.Qty, StopLoss: b.Close, OK: true}` (SL is a placeholder for the risk gate; engine doesn't use it on a close).

**SELL signal:**
- Long open → close it. (current behavior)
- No position → open new short. `qty = floor((equity × PositionFraction) / price, 6 dp)`. `SL = price × (1 + StopLossFraction)`. `TP = price × (1 − TakeProfitPct)` if configured. Copy `TrailActivationPct`/`TrailPct`.
- Short open → **skip** (`OK: false`). Mirror of how we don't pyramid longs.

The `Sizer` signature already exposes `positions []domain.Position`; no signature change.

### Risk — `internal/risk/checks.go`

`checkPositionSize` already uses `.Abs()`. No change.
`checkStopLoss` requires non-zero. Short SL is `price × (1 + StopLossFraction)` which is non-zero. No change.
No new sentinel errors.

### Frontend — `apps/frontend/src/pages/paper-trading/PaperPositionTable.tsx`

- Add `side` to the position row type (matches new backend field).
- Render a chip in the symbol/side column: `LONG` (green) for `side === "buy"`, `SHORT` (red) for `side === "sell"`.
- Existing PnL color logic stays the same — backend now computes PnL with the correct sign for shorts, so the cell's red/green driven by value sign is correct.

## Tests

### `internal/paper/engine_test.go`
- Open short, cover at profit → realized > 0, cash returns to roughly initial + profit.
- Open short, cover at loss → realized < 0.
- Open short, price rises to SL → auto-exit BUY fill, realized negative.
- Open short, price falls to TP → auto-exit BUY fill, realized positive.
- Open short, trail activates as price falls, then price rebounds to ratcheted SL → exit.
- `FlattenPositions` with one long + one short → both close, cash + 0 positions remain.
- `Equity()` with mixed long + short positions → equals manually computed sum.

### `internal/runtime/pipeline_test.go`
- SELL signal with no position → opens short (sizer returns OK, risk passes, order placed).
- Subsequent BUY signal → covers short (sizer returns pos.Qty).
- SELL signal while short already open → sizer returns OK=false, no order.

### `internal/risk/checks_test.go`
- Add case: short proposal at exactly the size boundary passes; just over fails.

## Out of scope

- Backtest engine (uses a separate paper engine instance but lives under `internal/backtest/`; the same change *will* compile/run there, but explicit backtest tests/UI for short are not in this slice).
- Live mode — Binance margin/futures plumbing, borrow fees, funding rates.
- Margin call / liquidation modeling.
- Symbol borrow availability checks.

## Risk policy implications

All existing risk checks apply to shorts as written:
- Position sizing: notional uses `.Abs()`, side-agnostic. ✓
- Daily drawdown: realized P&L is summed regardless of side. ✓
- Stop loss required: enforced via non-zero SL on the order. ✓
- Slippage check: market-order check, side-agnostic. ✓
- Kill switch: `FlattenPositions` updated to flatten shorts via BUY. ✓
