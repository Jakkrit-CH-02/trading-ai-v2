# Paper Short Selling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable SELL signals to open short positions in the paper trading engine, with symmetric SL/TP/trail logic and correct cash accounting.

**Architecture:** Add `Side` field to `domain.Position`; branch `Place()`, `OnBar()`, `CheckExits()`, and `FlattenPositions()` on position side; update `FixedFractionSizer` to open shorts on SELL with no position and cover on BUY with short; extend frontend position table with a LONG/SHORT chip.

**Tech Stack:** Go 1.22+, `github.com/shopspring/decimal`, React 18, MUI v5, Zod, Vitest

---

## File Map

| File | Change |
|---|---|
| `apps/backend/internal/domain/position.go` | Add `Side`, `TrailLow` fields |
| `apps/backend/internal/paper/engine.go` | Short logic in `Place`, `OnBar`, `CheckExits`, `Equity`, `FlattenPositions` |
| `apps/backend/internal/paper/engine_test.go` | Short-specific tests appended |
| `apps/backend/internal/runtime/pipeline.go` | `FixedFractionSizer` short-aware SELL and BUY branches |
| `apps/backend/internal/runtime/pipeline_test.go` | Sizer and pipeline short tests appended |
| `apps/frontend/src/api/paper.ts` | Add `side`, `trail_low` to `PaperPositionSchema` |
| `apps/frontend/src/pages/paper-trading/PaperPositionTable.tsx` | LONG/SHORT chip in Symbol column |

---

## Task 1 — Add `Side` and `TrailLow` to `domain.Position`

**Files:**
- Modify: `apps/backend/internal/domain/position.go`

- [ ] **Step 1: Add fields**

Replace the current `Position` struct in `apps/backend/internal/domain/position.go`:

```go
package domain

import "github.com/shopspring/decimal"

// Position is the net exposure on a symbol.
// Side == SideBuy means long; Side == SideSell means short.
// Zero-value Side is treated as SideBuy (long) for backwards compatibility.
type Position struct {
	Symbol       Symbol          `json:"symbol"`
	Side         Side            `json:"side"`
	Qty          decimal.Decimal `json:"qty"`
	AvgEntry     decimal.Decimal `json:"avg_entry"`
	UnrealizedPL decimal.Decimal `json:"unrealized_pl"`
	RealizedPL   decimal.Decimal `json:"realized_pl"`
	UpdatedMs    int64           `json:"updated_ms"`

	// Exit management fields. Set when the position is opened; updated each bar.
	StopLoss           decimal.Decimal `json:"stop_loss"`            // current SL level
	TakeProfit         decimal.Decimal `json:"take_profit"`          // fixed TP; zero = disabled
	TrailHigh          decimal.Decimal `json:"trail_high"`           // highest price since trail activated (longs)
	TrailLow           decimal.Decimal `json:"trail_low"`            // lowest price since trail activated (shorts)
	TrailActivationPct decimal.Decimal `json:"trail_activation_pct"` // profit % at which trail kicks in
	TrailPct           decimal.Decimal `json:"trail_pct"`            // trail distance from extreme
}
```

- [ ] **Step 2: Run existing tests to confirm no regressions**

```bash
cd apps/backend && go test ./internal/domain/... ./internal/paper/... ./internal/runtime/... ./internal/risk/...
```

Expected: all pass (new fields default to zero-value, backwards-compatible).

- [ ] **Step 3: Commit**

```bash
git add apps/backend/internal/domain/position.go
git commit -m "feat(domain): add Side and TrailLow fields to Position"
```

---

## Task 2 — Paper Engine: `Place()` short open and cover

**Files:**
- Modify: `apps/backend/internal/paper/engine.go`
- Modify: `apps/backend/internal/paper/engine_test.go`

- [ ] **Step 1: Write failing tests — append to `engine_test.go`**

```go
// ---- Short selling: Place ---------------------------------------------------

func sellOrder(qty, stopPrice, takeProfit, trailActivation, trailPct string) domain.Order {
	return domain.Order{
		Symbol:             sym,
		Side:               domain.SideSell,
		Type:               domain.OrderTypeMarket,
		Qty:                dec(qty),
		StopPrice:          dec(stopPrice),
		TakeProfit:         dec(takeProfit),
		TrailActivationPct: dec(trailActivation),
		TrailPct:           dec(trailPct),
		Mode:               domain.ModePaper,
	}
}

// seedShort opens a short after calling OnBar at price, drains the fill event.
func seedShort(t *testing.T, eng *Engine, price string, o domain.Order) {
	t.Helper()
	eng.OnBar(bar(price))
	_, err := eng.Place(context.Background(), o)
	require.NoError(t, err)
	<-eng.Events() // drain fill event
}

func TestPlace_Short_CreditsCash(t *testing.T) {
	eng := NewEngine(dec("100000"))
	eng.OnBar(bar("50000"))
	o := sellOrder("1", "52000", "0", "0", "0") // SL above entry for shorts
	initialCash := eng.Cash()
	_, err := eng.Place(context.Background(), o)
	require.NoError(t, err)
	// fill = 50000 * (1 - 0.0001) = 49995; cash increases
	require.True(t, eng.Cash().GreaterThan(initialCash), "opening short must credit cash")
}

func TestPlace_Short_SetsPositionFields(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("2", "105", "85", "0.01", "0.015"))

	positions := eng.Positions()
	require.Len(t, positions, 1)
	p := positions[0]
	require.Equal(t, domain.SideSell, p.Side)
	require.True(t, p.Qty.Equal(dec("2")))
	require.True(t, p.StopLoss.Equal(dec("105")))
	require.True(t, p.TakeProfit.Equal(dec("85")))
	require.True(t, p.TrailLow.IsPositive(), "TrailLow should be seeded at fill price")
}

func TestPlace_Cover_RealizesProfitWhenPriceFell(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Short at 100; price falls to 80; cover.
	seedShort(t, eng, "100", sellOrder("1", "105", "0", "0", "0"))
	cashAfterOpen := eng.Cash()

	eng.OnBar(bar("80"))
	buy := domain.Order{Symbol: sym, Side: domain.SideBuy, Type: domain.OrderTypeMarket, Qty: dec("1"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), buy)
	require.NoError(t, err)
	<-eng.Events()

	require.Empty(t, eng.Positions(), "position should be flat after cover")
	// covering at 80 < entry ~99.99 → profit → cash > cashAfterOpen
	require.True(t, eng.Cash().GreaterThan(cashAfterOpen), "covering at lower price should profit")
}

func TestPlace_Cover_RealizesLossWhenPriceRose(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Short at 100; price rises to 120; cover at a loss.
	seedShort(t, eng, "100", sellOrder("1", "110", "0", "0", "0"))
	cashAfterOpen := eng.Cash()

	eng.OnBar(bar("120"))
	buy := domain.Order{Symbol: sym, Side: domain.SideBuy, Type: domain.OrderTypeMarket, Qty: dec("1"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), buy)
	require.NoError(t, err)
	<-eng.Events()

	require.Empty(t, eng.Positions())
	require.True(t, eng.Cash().LessThan(cashAfterOpen), "covering at higher price should lose")
}

func TestPlace_Cover_PartialLeavesShortOpen(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("3", "110", "0", "0", "0"))

	eng.OnBar(bar("90"))
	buy := domain.Order{Symbol: sym, Side: domain.SideBuy, Type: domain.OrderTypeMarket, Qty: dec("1"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), buy)
	require.NoError(t, err)
	<-eng.Events()

	positions := eng.Positions()
	require.Len(t, positions, 1)
	require.True(t, positions[0].Qty.Equal(dec("2")), "2 of 3 still short")
	require.Equal(t, domain.SideSell, positions[0].Side)
}

func TestPlace_Cover_ExceedsQtyReturnsError(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("1", "110", "0", "0", "0"))

	eng.OnBar(bar("90"))
	buy := domain.Order{Symbol: sym, Side: domain.SideBuy, Type: domain.OrderTypeMarket, Qty: dec("5"), Mode: domain.ModePaper}
	_, err := eng.Place(context.Background(), buy)
	require.ErrorIs(t, err, ErrInsufficientPosition)
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/backend && go test ./internal/paper/... -run "TestPlace_Short|TestPlace_Cover" -v 2>&1 | tail -20
```

Expected: compile errors or test failures (Side/TrailLow fields exist but Place() doesn't handle them yet).

- [ ] **Step 3: Add `unrealizedPL` helper and update `Place()` in `engine.go`**

Add this helper just before `Place()`:

```go
// unrealizedPL computes the mark-to-market P&L for an open position.
// For longs: (mark - entry) * qty. For shorts: (entry - mark) * qty.
func unrealizedPL(pos *domain.Position, mark decimal.Decimal) decimal.Decimal {
	if pos.Side == domain.SideSell {
		return pos.AvgEntry.Sub(mark).Mul(pos.Qty)
	}
	return mark.Sub(pos.AvgEntry).Mul(pos.Qty)
}

// clearPositionExits resets all exit-management and side fields to zero.
func clearPositionExits(pos *domain.Position) {
	pos.Side = ""
	pos.AvgEntry = decimal.Zero
	pos.StopLoss = decimal.Zero
	pos.TakeProfit = decimal.Zero
	pos.TrailHigh = decimal.Zero
	pos.TrailLow = decimal.Zero
	pos.TrailActivationPct = decimal.Zero
	pos.TrailPct = decimal.Zero
}
```

Replace the `switch o.Side` block inside `Place()` (lines 212–244 in the current file) with:

```go
switch o.Side {
case domain.SideBuy:
	if pos.Side == domain.SideSell && pos.Qty.IsPositive() {
		// Cover short: buy-to-close.
		if o.Qty.GreaterThan(pos.Qty) {
			return domain.Order{}, fmt.Errorf("symbol=%s cover_qty=%s short_qty=%s: %w",
				o.Symbol, o.Qty.String(), pos.Qty.String(), ErrInsufficientPosition)
		}
		coverCost := o.Qty.Mul(fill)
		if coverCost.GreaterThan(e.cash) {
			return domain.Order{}, fmt.Errorf("symbol=%s cover_cost=%s cash=%s: %w",
				o.Symbol, coverCost.String(), e.cash.String(), ErrInsufficientCash)
		}
		realizedDelta = pos.AvgEntry.Sub(fill).Mul(o.Qty) // profit when price fell
		pos.RealizedPL = pos.RealizedPL.Add(realizedDelta)
		e.totalRealizedPL = e.totalRealizedPL.Add(realizedDelta)
		e.cash = e.cash.Sub(coverCost)
		pos.Qty = pos.Qty.Sub(o.Qty)
		if pos.Qty.IsZero() {
			clearPositionExits(pos)
		}
	} else {
		// Open or add to long.
		cost := o.Qty.Mul(fill)
		if cost.GreaterThan(e.cash) {
			return domain.Order{}, fmt.Errorf("symbol=%s qty=%s cost=%s cash=%s: %w",
				o.Symbol, o.Qty.String(), cost.String(), e.cash.String(), ErrInsufficientCash)
		}
		if pos.Qty.IsZero() {
			pos.Side = domain.SideBuy
		}
		newQty := pos.Qty.Add(o.Qty)
		pos.AvgEntry = pos.AvgEntry.Mul(pos.Qty).Add(fill.Mul(o.Qty)).Div(newQty)
		pos.Qty = newQty
		e.cash = e.cash.Sub(cost)
		pos.StopLoss = o.StopPrice
		pos.TakeProfit = o.TakeProfit
		pos.TrailActivationPct = o.TrailActivationPct
		pos.TrailPct = o.TrailPct
		pos.TrailHigh = fill
	}

case domain.SideSell:
	if pos.Side == domain.SideBuy && pos.Qty.IsPositive() {
		// Reduce or close long.
		if o.Qty.GreaterThan(pos.Qty) {
			return domain.Order{}, fmt.Errorf("symbol=%s qty=%s have=%s: %w",
				o.Symbol, o.Qty.String(), pos.Qty.String(), ErrInsufficientPosition)
		}
		realizedDelta = fill.Sub(pos.AvgEntry).Mul(o.Qty)
		pos.RealizedPL = pos.RealizedPL.Add(realizedDelta)
		e.totalRealizedPL = e.totalRealizedPL.Add(realizedDelta)
		e.cash = e.cash.Add(o.Qty.Mul(fill))
		pos.Qty = pos.Qty.Sub(o.Qty)
		if pos.Qty.IsZero() {
			clearPositionExits(pos)
		}
	} else {
		// Open or add to short: credit cash, track weighted-avg entry.
		if pos.Qty.IsZero() {
			pos.Side = domain.SideSell
			pos.AvgEntry = fill
			pos.Qty = o.Qty
			pos.TrailLow = fill
		} else {
			// Add to existing short.
			newQty := pos.Qty.Add(o.Qty)
			pos.AvgEntry = pos.AvgEntry.Mul(pos.Qty).Add(fill.Mul(o.Qty)).Div(newQty)
			pos.Qty = newQty
		}
		e.cash = e.cash.Add(o.Qty.Mul(fill))
		pos.StopLoss = o.StopPrice
		pos.TakeProfit = o.TakeProfit
		pos.TrailActivationPct = o.TrailActivationPct
		pos.TrailPct = o.TrailPct
	}
}
```

Also update the unrealized PnL line after the switch (currently `pos.UnrealizedPL = mark.Sub(pos.AvgEntry).Mul(pos.Qty)`):

```go
if !pos.Qty.IsZero() {
	pos.UnrealizedPL = unrealizedPL(pos, mark)
} else {
	pos.UnrealizedPL = decimal.Zero
}
```

- [ ] **Step 4: Run the new tests**

```bash
cd apps/backend && go test ./internal/paper/... -run "TestPlace_Short|TestPlace_Cover" -v 2>&1 | tail -30
```

Expected: all 6 new tests pass.

- [ ] **Step 5: Run full paper suite to confirm no regressions**

```bash
cd apps/backend && go test ./internal/paper/... -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/internal/paper/engine.go apps/backend/internal/paper/engine_test.go
git commit -m "feat(paper): short open and cover in Place()"
```

---

## Task 3 — Paper Engine: `OnBar()` short trail + `Equity()` short MTM

**Files:**
- Modify: `apps/backend/internal/paper/engine.go`
- Modify: `apps/backend/internal/paper/engine_test.go`

- [ ] **Step 1: Write failing tests — append to `engine_test.go`**

```go
// ---- Short trail: OnBar -----------------------------------------------------

func TestOnBar_Short_TrailActivates_SLRatchetsDown(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Short at 100; trail activates at -1% (99); trail distance 2%.
	seedShort(t, eng, "100", sellOrder("1", "105", "0", "0.01", "0.02"))
	initialSL := eng.Positions()[0].StopLoss // = 105 (hard SL above entry)

	// Price drops to 98 (below activation at 99). Trail should kick in.
	// newSL = 98 * (1 + 0.02) = 99.96, which is < 105, so SL should decrease.
	eng.OnBar(bar("98"))
	p := eng.Positions()[0]
	require.True(t, p.StopLoss.LessThan(initialSL),
		"trailing SL should fall below hard SL after activation: got %s", p.StopLoss)

	// Price drops further to 90. SL should ratchet down further.
	eng.OnBar(bar("90"))
	sl90 := eng.Positions()[0].StopLoss
	// newSL = 90 * (1 + 0.02) = 91.8
	expected90 := dec("91.8")
	require.True(t, sl90.LessThanOrEqual(expected90),
		"SL should trail to ~%s, got %s", expected90, sl90)

	// Price bounces back to 92 (still below SL 91.8 + eps). SL must NOT increase.
	eng.OnBar(bar("92"))
	slAfterBounce := eng.Positions()[0].StopLoss
	require.True(t, slAfterBounce.Equal(sl90),
		"SL must not increase on bounce for shorts: was %s, now %s", sl90, slAfterBounce)
}

func TestOnBar_Short_TrailDoesNotActivateBeforeThreshold(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Trail activates at -5% (95).
	seedShort(t, eng, "100", sellOrder("1", "110", "0", "0.05", "0.02"))
	initialSL := eng.Positions()[0].StopLoss

	// Price drops to 96 — above the activation level (95 = 100*(1-0.05)).
	eng.OnBar(bar("96"))
	require.True(t, eng.Positions()[0].StopLoss.Equal(initialSL),
		"SL must not change before activation threshold")
}

// ---- Equity with short positions --------------------------------------------

func TestEquity_ShortPosition_ReflectsUnrealizedGain(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Short 1 unit at 100.
	seedShort(t, eng, "100", sellOrder("1", "110", "0", "0", "0"))
	cashAfterOpen := eng.Cash() // cash > 100000 (received proceeds)

	// Price drops to 80 — unrealized profit for short.
	eng.OnBar(bar("80"))
	equity := eng.Equity()
	// Equity = cash + (entry - mark) * qty
	//        = cashAfterOpen + (fill ~99.99 - 80) * 1 ≈ cashAfterOpen + ~19.99
	require.True(t, equity.GreaterThan(cashAfterOpen),
		"equity should exceed cash alone when short is profitable: equity=%s cash=%s", equity, cashAfterOpen)
}

func TestEquity_ShortPosition_ReflectsUnrealizedLoss(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("1", "110", "0", "0", "0"))
	cashAfterOpen := eng.Cash()

	// Price rises to 120 — unrealized loss for short.
	eng.OnBar(bar("120"))
	equity := eng.Equity()
	// Equity = cash + (fill ~99.99 - 120) * 1 = cash - ~20.01
	require.True(t, equity.LessThan(cashAfterOpen),
		"equity should be less than cash when short is losing: equity=%s cash=%s", equity, cashAfterOpen)
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/backend && go test ./internal/paper/... -run "TestOnBar_Short|TestEquity_Short" -v 2>&1 | tail -20
```

Expected: failures (trail logic not implemented for shorts yet; equity formula only handles longs).

- [ ] **Step 3: Update `OnBar()` to advance trail for shorts**

In `engine.go`, replace the trail block inside `OnBar()` (the `if p.TrailPct.IsPositive()` section):

```go
if p.TrailPct.IsPositive() && p.AvgEntry.IsPositive() {
	one := decimal.NewFromInt(1)
	if p.Side == domain.SideSell {
		// Short trail: activate when price falls below entry*(1-activationPct).
		activation := p.AvgEntry.Mul(one.Sub(p.TrailActivationPct))
		if b.Close.LessThan(activation) {
			if p.TrailLow.IsZero() || b.Close.LessThan(p.TrailLow) {
				p.TrailLow = b.Close
			}
			newSL := p.TrailLow.Mul(one.Add(p.TrailPct))
			if p.StopLoss.IsZero() || newSL.LessThan(p.StopLoss) {
				p.StopLoss = newSL
			}
		}
	} else {
		// Long trail: activate when price rises above entry*(1+activationPct).
		activation := p.AvgEntry.Mul(one.Add(p.TrailActivationPct))
		if b.Close.GreaterThan(activation) {
			if b.Close.GreaterThan(p.TrailHigh) {
				p.TrailHigh = b.Close
			}
			newSL := p.TrailHigh.Mul(one.Sub(p.TrailPct))
			if newSL.GreaterThan(p.StopLoss) {
				p.StopLoss = newSL
			}
		}
	}
}
```

Also update the unrealized PnL line in `OnBar()` (currently `p.UnrealizedPL = b.Close.Sub(p.AvgEntry).Mul(p.Qty)`):

```go
p.UnrealizedPL = unrealizedPL(p, b.Close)
```

- [ ] **Step 4: Update `Equity()` to handle short positions**

Replace the inner loop in `Equity()`:

```go
for sym, p := range e.positions {
	if p.Qty.IsZero() {
		continue
	}
	px, ok := e.lastClose[sym]
	if !ok {
		px = p.AvgEntry
	}
	if p.Side == domain.SideSell {
		// Short: cash already holds the sale proceeds.
		// Add only the unrealized component: (entry - mark) * qty.
		eq = eq.Add(p.AvgEntry.Sub(px).Mul(p.Qty))
	} else {
		eq = eq.Add(p.Qty.Mul(px))
	}
}
```

- [ ] **Step 5: Run the new tests**

```bash
cd apps/backend && go test ./internal/paper/... -run "TestOnBar_Short|TestEquity_Short" -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Run full paper suite**

```bash
cd apps/backend && go test ./internal/paper/... 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/internal/paper/engine.go apps/backend/internal/paper/engine_test.go
git commit -m "feat(paper): short trail in OnBar() + short-aware Equity()"
```

---

## Task 4 — Paper Engine: `CheckExits()` short exits + `FlattenPositions()` short flatten

**Files:**
- Modify: `apps/backend/internal/paper/engine.go`
- Modify: `apps/backend/internal/paper/engine_test.go`

- [ ] **Step 1: Write failing tests — append to `engine_test.go`**

```go
// ---- Short CheckExits -------------------------------------------------------

func TestCheckExits_Short_StopLoss_Triggers_WhenPriceRises(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Short at 100, SL at 105 (above entry).
	seedShort(t, eng, "100", sellOrder("1", "105", "0", "0", "0"))

	// Price rises to 108 (above SL 105).
	orders, err := eng.CheckExits(context.Background(), bar("108"))
	require.NoError(t, err)
	require.Len(t, orders, 1)
	require.Equal(t, domain.SideBuy, orders[0].Side, "short SL exit must be a BUY (cover)")
	require.Equal(t, domain.OrderStatusFilled, orders[0].Status)
	require.Empty(t, eng.Positions(), "position should be flat after short SL exit")

	evt := <-eng.Events()
	require.Equal(t, "stop_loss", evt.ExitReason)
	require.Equal(t, domain.SideBuy, evt.Side)
}

func TestCheckExits_Short_StopLoss_NoTrigger_WhenPriceFalls(t *testing.T) {
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("1", "105", "0", "0", "0"))

	// Price falls to 90 — moving in our favour, SL should not fire.
	orders, err := eng.CheckExits(context.Background(), bar("90"))
	require.NoError(t, err)
	require.Empty(t, orders)
	require.Len(t, eng.Positions(), 1)
}

func TestCheckExits_Short_TakeProfit_Triggers_WhenPriceFalls(t *testing.T) {
	eng := NewEngine(dec("100000"))
	// Short at 100, TP at 85 (below entry).
	seedShort(t, eng, "100", sellOrder("1", "110", "85", "0", "0"))

	// Price drops to 82 (below TP 85).
	orders, err := eng.CheckExits(context.Background(), bar("82"))
	require.NoError(t, err)
	require.Len(t, orders, 1)
	require.Equal(t, domain.SideBuy, orders[0].Side, "short TP exit must be a BUY")
	require.Empty(t, eng.Positions())

	evt := <-eng.Events()
	require.Equal(t, "take_profit", evt.ExitReason)
}

func TestCheckExits_Short_Trail_ThenSLFires(t *testing.T) {
	ctx := context.Background()
	eng := NewEngine(dec("100000"))
	// Short at 100; trail activates at -1%; trail dist 2%.
	seedShort(t, eng, "100", sellOrder("1", "105", "0", "0.01", "0.02"))

	// Price falls to 90 — trail activates, SL ratchets to 90*(1+0.02)=91.8.
	eng.OnBar(bar("90"))
	raisedDownSL := eng.Positions()[0].StopLoss
	require.True(t, raisedDownSL.LessThan(dec("105")), "SL should have moved down: %s", raisedDownSL)

	// Price bounces above the ratcheted SL → short SL fires.
	trigger := raisedDownSL.Add(dec("1")) // slightly above SL
	orders, err := eng.CheckExits(ctx, bar(trigger.String()))
	require.NoError(t, err)
	require.Len(t, orders, 1, "short trailing SL should trigger on bounce above ratcheted level")
	evt := <-eng.Events()
	require.Equal(t, "stop_loss", evt.ExitReason)
}

// ---- FlattenPositions: short -----------------------------------------------

func TestFlattenPositions_FlattensShort(t *testing.T) {
	ctx := context.Background()
	eng := NewEngine(dec("100000"))
	seedShort(t, eng, "100", sellOrder("1", "110", "0", "0", "0"))
	require.Len(t, eng.Positions(), 1)

	err := eng.FlattenPositions(ctx)
	require.NoError(t, err)
	require.Empty(t, eng.Positions(), "short should be flat after FlattenPositions")
}

func TestFlattenPositions_FlattensMixedPortfolio(t *testing.T) {
	ctx := context.Background()
	eng := NewEngine(dec("200000"))

	// Open a long on sym (BTCUSDT).
	eng.OnBar(bar("100"))
	_, err := eng.Place(ctx, buyOrder("1", "90", "0", "0", "0"))
	require.NoError(t, err)
	<-eng.Events()

	// Open a short on a different symbol.
	sym2 := domain.Symbol("ETHUSDT")
	eng.lastClose[sym2] = dec("50") // inject price directly for test
	shortOnSym2 := domain.Order{
		Symbol:    sym2,
		Side:      domain.SideSell,
		Type:      domain.OrderTypeMarket,
		Qty:       dec("2"),
		StopPrice: dec("55"),
		Mode:      domain.ModePaper,
	}
	_, err = eng.Place(ctx, shortOnSym2)
	require.NoError(t, err)
	<-eng.Events()

	require.Len(t, eng.Positions(), 2)

	err = eng.FlattenPositions(ctx)
	require.NoError(t, err)
	require.Empty(t, eng.Positions(), "all positions should be flat")
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/backend && go test ./internal/paper/... -run "TestCheckExits_Short|TestFlattenPositions" -v 2>&1 | tail -20
```

Expected: failures on short-specific cases (CheckExits uses SideSell for exits, wrong direction for shorts).

- [ ] **Step 3: Update `CheckExits()` in `engine.go`**

Replace the exit condition block and fill logic inside `CheckExits()`. The full updated body after the opening guard:

```go
pos, ok := e.positions[b.Symbol]
if !ok || pos.Qty.IsZero() {
	return nil, nil
}

price := b.Close
one := decimal.NewFromInt(1)
bp := decimal.New(int64(spreadBps), -4)

var exitReason string
var exitSide domain.Side
var fill decimal.Decimal

if pos.Side == domain.SideSell {
	// Short exits: SL fires when price rises to/above SL; TP fires when price falls to/below TP.
	switch {
	case pos.StopLoss.IsPositive() && price.GreaterThanOrEqual(pos.StopLoss):
		exitReason = "stop_loss"
	case pos.TakeProfit.IsPositive() && price.LessThanOrEqual(pos.TakeProfit):
		exitReason = "take_profit"
	}
	exitSide = domain.SideBuy
	fill = price.Mul(one.Add(bp)) // buy-to-cover pays the spread
} else {
	// Long exits: SL fires when price falls to/below SL; TP fires when price rises to/above TP.
	switch {
	case pos.StopLoss.IsPositive() && price.LessThanOrEqual(pos.StopLoss):
		exitReason = "stop_loss"
	case pos.TakeProfit.IsPositive() && price.GreaterThanOrEqual(pos.TakeProfit):
		exitReason = "take_profit"
	}
	exitSide = domain.SideSell
	fill = price.Mul(one.Sub(bp)) // sell pays the spread
}

if exitReason == "" {
	return nil, nil
}

qty := pos.Qty
var realizedDelta decimal.Decimal
if pos.Side == domain.SideSell {
	// Cover short: debit cash, realized = (entry - fill) * qty.
	realizedDelta = pos.AvgEntry.Sub(fill).Mul(qty)
	e.cash = e.cash.Sub(qty.Mul(fill))
} else {
	// Close long: credit cash, realized = (fill - entry) * qty.
	realizedDelta = fill.Sub(pos.AvgEntry).Mul(qty)
	e.cash = e.cash.Add(qty.Mul(fill))
}

e.totalRealizedPL = e.totalRealizedPL.Add(realizedDelta)
pos.RealizedPL = pos.RealizedPL.Add(realizedDelta)
pos.Qty = decimal.Zero
pos.UnrealizedPL = decimal.Zero
clearPositionExits(pos)
now := timex.NowMs()
pos.UpdatedMs = now

orderID := ids.New()
evt := TradeLogEvent{
	OrderID:     orderID,
	Symbol:      b.Symbol,
	Side:        exitSide,
	Qty:         qty,
	FillPrice:   fill,
	Cash:        e.cash,
	RealizedPL:  realizedDelta,
	TimestampMs: now,
	ExitReason:  exitReason,
}
select {
case e.events <- evt:
default:
	slog.WarnContext(ctx, "paper event channel full, dropping exit event",
		"service", "paper",
		"mode", string(domain.ModePaper),
		"symbol", string(b.Symbol),
		"order_id", orderID,
	)
}

slog.InfoContext(ctx, "paper auto-exit",
	"service", "paper",
	"mode", string(domain.ModePaper),
	"symbol", string(b.Symbol),
	"reason", exitReason,
	"side", string(exitSide),
	"qty", qty.String(),
	"fill_price", fill.String(),
	"realized_delta", realizedDelta.String(),
)

exitOrder := domain.Order{
	ID:         orderID,
	Symbol:     b.Symbol,
	Side:       exitSide,
	Type:       domain.OrderTypeMarket,
	Qty:        qty,
	Price:      fill,
	Status:     domain.OrderStatusFilled,
	Mode:       domain.ModePaper,
	CreatedMs:  now,
	UpdatedMs:  now,
	ExchangeID: "paper-exit-" + exitReason + "-" + orderID,
}
return []domain.Order{exitOrder}, nil
```

- [ ] **Step 4: Update `FlattenPositions()` to send BUY for shorts**

Replace the inner loop in `FlattenPositions()`:

```go
for _, w := range work {
	exitSide := domain.SideSell
	if w.side == domain.SideSell {
		exitSide = domain.SideBuy
	}
	// w is type flatEntry, not domain.Position
	exit := domain.Order{
		ID:     "kill-" + string(w.sym),
		Symbol: w.sym,
		Side:   exitSide,
		Type:   domain.OrderTypeMarket,
		Qty:    w.qty,
		Mode:   domain.ModePaper,
	}
	if _, err := e.Place(ctx, exit); err != nil { ... }
}
```

This requires the `sell` struct in `FlattenPositions` to carry the side. Update the struct and collection loop:

```go
type flatEntry struct {
	sym  domain.Symbol
	qty  decimal.Decimal
	side domain.Side
}
var work []flatEntry
for sym, p := range e.positions {
	if p.Qty.IsZero() {
		continue
	}
	work = append(work, flatEntry{sym: sym, qty: p.Qty, side: p.Side})
}
```

- [ ] **Step 5: Run the new tests**

```bash
cd apps/backend && go test ./internal/paper/... -run "TestCheckExits_Short|TestFlattenPositions" -v 2>&1 | tail -30
```

Expected: all pass.

- [ ] **Step 6: Run full paper suite**

```bash
cd apps/backend && go test ./internal/paper/... 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/internal/paper/engine.go apps/backend/internal/paper/engine_test.go
git commit -m "feat(paper): short CheckExits and FlattenPositions"
```

---

## Task 5 — Sizer: short-aware `FixedFractionSizer`

**Files:**
- Modify: `apps/backend/internal/runtime/pipeline.go`
- Modify: `apps/backend/internal/runtime/pipeline_test.go`

- [ ] **Step 1: Write failing tests — append to `pipeline_test.go`**

```go
// ---- FixedFractionSizer: short selling --------------------------------------

func TestFixedFractionSizer_SellNoPosition_OpenShort(t *testing.T) {
	cfg := PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.03),
		TakeProfitPct:    decimal.NewFromFloat(0.06),
		TrailActivationPct: decimal.NewFromFloat(0.02),
		TrailPct:           decimal.NewFromFloat(0.015),
	}
	sizer := FixedFractionSizer(cfg)

	b := domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(1000)}
	equity := decimal.NewFromInt(10000) // 10% of 10000 = 1000 / 1000 price = 1 unit

	sig := domain.Signal{Symbol: "BTCUSDT", Action: domain.SignalActionSell}
	result := sizer(sig, domain.SideSell, b, equity, nil)

	require.True(t, result.OK, "SELL with no position should open a short")
	require.True(t, result.Qty.GreaterThan(decimal.Zero))

	one := decimal.NewFromInt(1)
	expectedSL := decimal.NewFromInt(1000).Mul(one.Add(decimal.NewFromFloat(0.03)))
	require.True(t, result.StopLoss.Equal(expectedSL), "SL should be above entry for shorts: got %s", result.StopLoss)

	expectedTP := decimal.NewFromInt(1000).Mul(one.Sub(decimal.NewFromFloat(0.06)))
	require.True(t, result.TakeProfit.Equal(expectedTP), "TP should be below entry for shorts: got %s", result.TakeProfit)
}

func TestFixedFractionSizer_SellShortAlreadyOpen_Skips(t *testing.T) {
	cfg := PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.03),
	}
	sizer := FixedFractionSizer(cfg)

	b := domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(1000)}
	equity := decimal.NewFromInt(10000)
	existingShort := []domain.Position{{Symbol: "BTCUSDT", Side: domain.SideSell, Qty: decimal.NewFromInt(1)}}

	sig := domain.Signal{Symbol: "BTCUSDT", Action: domain.SignalActionSell}
	result := sizer(sig, domain.SideSell, b, equity, existingShort)

	require.False(t, result.OK, "SELL with existing short should skip (no pyramid)")
}

func TestFixedFractionSizer_BuyWithShortOpen_CoverSize(t *testing.T) {
	cfg := PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.03),
	}
	sizer := FixedFractionSizer(cfg)

	b := domain.Bar{Symbol: "BTCUSDT", Close: decimal.NewFromInt(1000)}
	equity := decimal.NewFromInt(10000)
	existingShort := []domain.Position{{Symbol: "BTCUSDT", Side: domain.SideSell, Qty: decimal.NewFromInt(2)}}

	sig := domain.Signal{Symbol: "BTCUSDT", Action: domain.SignalActionBuy}
	result := sizer(sig, domain.SideBuy, b, equity, existingShort)

	require.True(t, result.OK, "BUY with existing short should cover")
	require.True(t, result.Qty.Equal(decimal.NewFromInt(2)), "cover qty must match short qty: got %s", result.Qty)
	require.True(t, result.StopLoss.IsPositive(), "StopLoss placeholder must be non-zero for risk gate")
}
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd apps/backend && go test ./internal/runtime/... -run "TestFixedFractionSizer_Sell|TestFixedFractionSizer_Buy" -v 2>&1 | tail -20
```

Expected: failures (sizer returns OK=false for SELL with no position; BUY with short open returns OK=false too).

- [ ] **Step 3: Update `FixedFractionSizer` in `pipeline.go`**

Replace the entire `FixedFractionSizer` function:

```go
// FixedFractionSizer is the default sizer:
//
//   - BUY, no/long position: qty = floor((equity * PositionFraction) / price, 6 dp)
//     sl = price * (1 - StopLossFraction), tp = price * (1 + TakeProfitPct)
//   - BUY, short position open: qty = short.Qty (cover), sl = bar close (placeholder)
//   - SELL, long position open: qty = long.Qty (close), sl = bar close (placeholder)
//   - SELL, no position: qty = floor((equity * PositionFraction) / price, 6 dp)
//     sl = price * (1 + StopLossFraction), tp = price * (1 - TakeProfitPct)
//   - SELL, short already open: skip (OK=false, no pyramid)
func FixedFractionSizer(cfg PipelineConfig) Sizer {
	one := decimal.NewFromInt(1)
	return func(_ domain.Signal, side domain.Side, b domain.Bar, equity decimal.Decimal, positions []domain.Position) SizerResult {
		switch side {
		case domain.SideBuy:
			// Check if there's an open short to cover.
			for _, p := range positions {
				if p.Symbol == b.Symbol && p.Side == domain.SideSell && p.Qty.GreaterThan(decimal.Zero) {
					return SizerResult{Qty: p.Qty, StopLoss: b.Close, OK: true}
				}
			}
			// No short: open/add to long.
			if equity.LessThanOrEqual(decimal.Zero) || b.Close.LessThanOrEqual(decimal.Zero) {
				return SizerResult{}
			}
			qty := equity.Mul(cfg.PositionFraction).Div(b.Close).Truncate(6)
			if qty.LessThanOrEqual(decimal.Zero) {
				return SizerResult{}
			}
			sl := b.Close.Mul(one.Sub(cfg.StopLossFraction))
			var tp decimal.Decimal
			if cfg.TakeProfitPct.IsPositive() {
				tp = b.Close.Mul(one.Add(cfg.TakeProfitPct))
			}
			return SizerResult{
				Qty:                qty,
				StopLoss:           sl,
				TakeProfit:         tp,
				TrailActivationPct: cfg.TrailActivationPct,
				TrailPct:           cfg.TrailPct,
				OK:                 true,
			}

		case domain.SideSell:
			// Check if there's a long to close.
			for _, p := range positions {
				if p.Symbol == b.Symbol && (p.Side == domain.SideBuy || p.Side == "") && p.Qty.GreaterThan(decimal.Zero) {
					return SizerResult{Qty: p.Qty, StopLoss: b.Close, OK: true}
				}
			}
			// Check if short already open — skip (no pyramid).
			for _, p := range positions {
				if p.Symbol == b.Symbol && p.Side == domain.SideSell && p.Qty.GreaterThan(decimal.Zero) {
					return SizerResult{}
				}
			}
			// No position: open short.
			if equity.LessThanOrEqual(decimal.Zero) || b.Close.LessThanOrEqual(decimal.Zero) {
				return SizerResult{}
			}
			qty := equity.Mul(cfg.PositionFraction).Div(b.Close).Truncate(6)
			if qty.LessThanOrEqual(decimal.Zero) {
				return SizerResult{}
			}
			sl := b.Close.Mul(one.Add(cfg.StopLossFraction))
			var tp decimal.Decimal
			if cfg.TakeProfitPct.IsPositive() {
				tp = b.Close.Mul(one.Sub(cfg.TakeProfitPct))
			}
			return SizerResult{
				Qty:                qty,
				StopLoss:           sl,
				TakeProfit:         tp,
				TrailActivationPct: cfg.TrailActivationPct,
				TrailPct:           cfg.TrailPct,
				OK:                 true,
			}

		default:
			return SizerResult{}
		}
	}
}
```

- [ ] **Step 4: Run the new tests**

```bash
cd apps/backend && go test ./internal/runtime/... -run "TestFixedFractionSizer" -v 2>&1 | tail -20
```

Expected: all 3 new tests pass.

- [ ] **Step 5: Run full runtime suite**

```bash
cd apps/backend && go test ./internal/runtime/... 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 6: Run full backend suite**

```bash
cd apps/backend && go test ./... 2>&1 | tail -15
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/internal/runtime/pipeline.go apps/backend/internal/runtime/pipeline_test.go
git commit -m "feat(runtime): short-aware FixedFractionSizer"
```

---

## Task 6 — Frontend: `side` field + SHORT chip in position table

**Files:**
- Modify: `apps/frontend/src/api/paper.ts`
- Modify: `apps/frontend/src/pages/paper-trading/PaperPositionTable.tsx`

- [ ] **Step 1: Add `side` and `trail_low` to schema in `paper.ts`**

In `apps/frontend/src/api/paper.ts`, replace `PaperPositionSchema`:

```ts
export const PaperPositionSchema = z.object({
  symbol: z.string(),
  side: z.enum(["buy", "sell"]).optional().default("buy"),
  qty: z.string(),
  avg_entry: z.string(),
  unrealized_pl: z.string(),
  realized_pl: z.string(),
  updated_ms: z.number().int(),
  stop_loss: z.string().optional().default("0"),
  take_profit: z.string().optional().default("0"),
  trail_high: z.string().optional().default("0"),
  trail_low: z.string().optional().default("0"),
});
```

- [ ] **Step 2: Update `PaperPositionTable.tsx` to show SHORT chip**

Replace the entire file content of `apps/frontend/src/pages/paper-trading/PaperPositionTable.tsx`:

```tsx
import {
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { PaperPosition } from "../../api/paper";
import { formatMoney, formatPrice, formatTime } from "../../lib/format";

export interface PaperPositionTableProps {
  positions: PaperPosition[];
}

const styles = {
  empty: { color: "text.secondary", py: 3, textAlign: "center" },
} as const;

function pnlColor(value: string): "success.main" | "error.main" | "text.primary" {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text.primary";
  return n > 0 ? "success.main" : "error.main";
}

function priceOrDash(v: string | undefined): string {
  if (!v || v === "0" || v === "0.00") return "—";
  return formatPrice(v);
}

export default function PaperPositionTable(props: PaperPositionTableProps) {
  const { positions } = props;
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
          Open Positions
        </Typography>
        {positions.length === 0 ? (
          <Typography sx={styles.empty}>No open positions.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Avg Entry</TableCell>
                <TableCell align="right">Stop Loss</TableCell>
                <TableCell align="right">Trail</TableCell>
                <TableCell align="right">Take Profit</TableCell>
                <TableCell align="right">Unrealized P&L</TableCell>
                <TableCell align="right">Realized P&L</TableCell>
                <TableCell align="right">Updated</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {positions.map((p) => (
                <TableRow key={p.symbol}>
                  <TableCell>
                    <Typography component="span" sx={{ fontWeight: 600, mr: 1 }}>
                      {p.symbol}
                    </Typography>
                    <Chip
                      label={p.side === "sell" ? "SHORT" : "LONG"}
                      size="small"
                      sx={{
                        bgcolor: p.side === "sell" ? "error.main" : "success.main",
                        color: "common.white",
                        fontWeight: 700,
                        fontSize: "0.65rem",
                        height: 18,
                      }}
                    />
                  </TableCell>
                  <TableCell align="right">{formatPrice(p.qty)}</TableCell>
                  <TableCell align="right">{formatPrice(p.avg_entry)}</TableCell>
                  <TableCell align="right" sx={{ color: "error.main" }}>
                    {priceOrDash(p.stop_loss)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: "info.main" }}>
                    {p.side === "sell"
                      ? priceOrDash(p.trail_low)
                      : priceOrDash(p.trail_high)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: "success.main" }}>
                    {priceOrDash(p.take_profit)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: pnlColor(p.unrealized_pl) }}>
                    {formatMoney(p.unrealized_pl)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: pnlColor(p.realized_pl) }}>
                    {formatMoney(p.realized_pl)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: "text.secondary" }}>
                    {formatTime(p.updated_ms)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
```

Note: "Trail High" header renamed to "Trail" — shows `trail_low` for shorts and `trail_high` for longs.

- [ ] **Step 3: Type-check**

```bash
cd apps/frontend && pnpm typecheck 2>&1 | tail -10
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/api/paper.ts apps/frontend/src/pages/paper-trading/PaperPositionTable.tsx
git commit -m "feat(frontend): LONG/SHORT chip in position table; add side + trail_low to schema"
```

---

## Final Verification

- [ ] **Run full backend test suite**

```bash
cd apps/backend && go test ./... 2>&1 | grep -E "FAIL|ok"
```

Expected: all lines show `ok`.

- [ ] **Run frontend typecheck and tests**

```bash
cd apps/frontend && pnpm typecheck && pnpm test:ci 2>&1 | tail -15
```

Expected: no type errors, all tests pass.
