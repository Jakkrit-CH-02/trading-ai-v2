package paper

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
)

var (
	ErrInsufficientCash     = errors.New("paper: insufficient cash")
	ErrInsufficientPosition = errors.New("paper: insufficient position to sell")
	ErrNoMarketPrice        = errors.New("paper: no market price for symbol")
	ErrUnknownSide          = errors.New("paper: unknown order side")
)

// spreadBps is the simulated half-spread applied on top of the bar close.
// Buys fill at close*(1+1bp); sells fill at close*(1-1bp).
const spreadBps = 1

// eventBuffer is the capacity of the trade-log event channel. Slow consumers
// will see events dropped (and a warn log) rather than blocking the engine.
const eventBuffer = 256

// TradeLogEvent is emitted on every simulated fill. It is the input to the
// trade-log service and any UI subscribers. Decimal values are by-value copies
// of the engine's state at fill time — safe to read without holding the lock.
type TradeLogEvent struct {
	OrderID     string          `json:"order_id"`
	Symbol      domain.Symbol   `json:"symbol"`
	Side        domain.Side     `json:"side"`
	Qty         decimal.Decimal `json:"qty"`
	FillPrice   decimal.Decimal `json:"fill_price"`
	StopPrice   decimal.Decimal `json:"stop_price"`   // SL set on buy; zero for sells
	TakeProfit  decimal.Decimal `json:"take_profit"`  // TP set on buy; zero for sells
	Cash        decimal.Decimal `json:"cash"`
	RealizedPL  decimal.Decimal `json:"realized_pl"`
	TimestampMs int64           `json:"timestamp_ms"`
	ExitReason  string          `json:"exit_reason,omitempty"` // "stop_loss" | "take_profit" | ""
}

// Engine is the paper-mode order executor. It maintains a virtual cash
// balance, open positions per symbol, and emits a TradeLogEvent on every fill.
// Engine implements order.Executor.
type Engine struct {
	mu        sync.Mutex
	cash      decimal.Decimal
	initial   decimal.Decimal
	positions map[domain.Symbol]*domain.Position
	lastClose map[domain.Symbol]decimal.Decimal
	events    chan TradeLogEvent

	// Daily P&L tracking. totalRealizedPL is the cumulative sum of all fills.
	// dayStartPL is the snapshot taken at the start of the current UTC day.
	// currentDayUTC is unix-ms / 86_400_000 for the day of the last snapshot.
	totalRealizedPL decimal.Decimal
	dayStartPL      decimal.Decimal
	currentDayUTC   int64
}

func NewEngine(initialCash decimal.Decimal) *Engine {
	return &Engine{
		cash:          initialCash,
		initial:       initialCash,
		positions:     make(map[domain.Symbol]*domain.Position),
		lastClose:     make(map[domain.Symbol]decimal.Decimal),
		events:        make(chan TradeLogEvent, eventBuffer),
		currentDayUTC: timex.NowMs() / 86_400_000,
	}
}

// Events returns the read end of the trade-log channel.
func (e *Engine) Events() <-chan TradeLogEvent { return e.events }

// Cash returns the current cash balance (excluding open positions).
func (e *Engine) Cash() decimal.Decimal {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.cash
}

// Initial returns the starting cash balance.
func (e *Engine) Initial() decimal.Decimal {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.initial
}

// OnBar feeds the latest bar so the engine can mark positions and advance the
// trailing stop. Must be called at least once per symbol before Place.
func (e *Engine) OnBar(b domain.Bar) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.lastClose[b.Symbol] = b.Close
	p, ok := e.positions[b.Symbol]
	if !ok || p.Qty.IsZero() {
		return
	}
	p.UnrealizedPL = unrealizedPL(p, b.Close)
	p.UpdatedMs = b.CloseTime

	// Advance trail: side-aware trailing stop logic.
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
}

// Balance returns the virtual cash balance.
func (e *Engine) Balance() decimal.Decimal {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.cash
}

// DailyPnL returns the net realized P&L since the start of the current UTC day.
// Negative means a net loss today. Resets automatically at UTC midnight.
func (e *Engine) DailyPnL() decimal.Decimal {
	e.mu.Lock()
	defer e.mu.Unlock()
	today := timex.NowMs() / 86_400_000
	if today != e.currentDayUTC {
		e.dayStartPL = e.totalRealizedPL
		e.currentDayUTC = today
	}
	return e.totalRealizedPL.Sub(e.dayStartPL)
}

// Equity returns cash + sum(position.qty * lastClose) — the mark-to-market
// portfolio value.
func (e *Engine) Equity() decimal.Decimal {
	e.mu.Lock()
	defer e.mu.Unlock()
	eq := e.cash
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
	return eq
}

// Positions returns a snapshot of open (non-zero qty) positions.
func (e *Engine) Positions() []domain.Position {
	e.mu.Lock()
	defer e.mu.Unlock()
	out := make([]domain.Position, 0, len(e.positions))
	for _, p := range e.positions {
		if p.Qty.IsZero() {
			continue
		}
		out = append(out, *p)
	}
	return out
}

// unrealizedPL computes the mark-to-market P&L for an open position.
// For longs: (mark - entry) * qty. For shorts: (entry - mark) * qty.
func unrealizedPL(pos *domain.Position, mark decimal.Decimal) decimal.Decimal {
	if pos.Side == domain.SideSell {
		return pos.AvgEntry.Sub(mark).Mul(pos.Qty)
	}
	return mark.Sub(pos.AvgEntry).Mul(pos.Qty)
}

// clearPosition resets all position state to zero when a position is fully closed.
func clearPosition(pos *domain.Position) {
	pos.Side = ""
	pos.AvgEntry = decimal.Zero
	pos.StopLoss = decimal.Zero
	pos.TakeProfit = decimal.Zero
	pos.TrailHigh = decimal.Zero
	pos.TrailLow = decimal.Zero
	pos.TrailActivationPct = decimal.Zero
	pos.TrailPct = decimal.Zero
}

// Place simulates execution of an Order against the latest bar close, applying
// a 1bp spread and updating cash, position, P&L, and the event channel.
// Implements order.Executor.
func (e *Engine) Place(ctx context.Context, o domain.Order) (domain.Order, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	mark, ok := e.lastClose[o.Symbol]
	if !ok {
		return domain.Order{}, fmt.Errorf("symbol=%s: %w", o.Symbol, ErrNoMarketPrice)
	}

	bp := decimal.New(int64(spreadBps), -4) // 1 bp = 0.0001
	one := decimal.NewFromInt(1)

	var fill decimal.Decimal
	switch o.Side {
	case domain.SideBuy:
		fill = mark.Mul(one.Add(bp))
	case domain.SideSell:
		fill = mark.Mul(one.Sub(bp))
	default:
		return domain.Order{}, fmt.Errorf("side=%q: %w", o.Side, ErrUnknownSide)
	}

	pos, ok := e.positions[o.Symbol]
	if !ok {
		pos = &domain.Position{Symbol: o.Symbol}
		e.positions[o.Symbol] = pos
	}

	now := timex.NowMs()
	var realizedDelta decimal.Decimal

	switch o.Side {
	case domain.SideBuy:
		if pos.Side == domain.SideSell && pos.Qty.IsPositive() {
			// Cover short: buy-to-close.
			if o.Qty.GreaterThan(pos.Qty) {
				return domain.Order{}, fmt.Errorf("symbol=%s cover_qty=%s short_qty=%s: %w",
					o.Symbol, o.Qty.String(), pos.Qty.String(), ErrInsufficientPosition)
			}
			// P&L = (avgEntry - fill) * qty: positive when price fell (profit), negative when rose (loss).
			// The short-open already credited qty*fillOpen to cash; on cover we must debit the full
			// gross cover cost (qty*fillCover). Net round-trip P&L = qty*(fillOpen-fillCover).
			coverCost := o.Qty.Mul(fill)
			if coverCost.GreaterThan(e.cash) {
				return domain.Order{}, fmt.Errorf("symbol=%s cover_cost=%s cash=%s: %w",
					o.Symbol, coverCost.String(), e.cash.String(), ErrInsufficientCash)
			}
			realizedDelta = pos.AvgEntry.Sub(fill).Mul(o.Qty)
			pos.RealizedPL = pos.RealizedPL.Add(realizedDelta)
			e.totalRealizedPL = e.totalRealizedPL.Add(realizedDelta)
			e.cash = e.cash.Sub(coverCost)
			pos.Qty = pos.Qty.Sub(o.Qty)
			if pos.Qty.IsZero() {
				clearPosition(pos)
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
				clearPosition(pos)
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

	if !pos.Qty.IsZero() {
		pos.UnrealizedPL = unrealizedPL(pos, mark)
	} else {
		pos.UnrealizedPL = decimal.Zero
	}
	pos.UpdatedMs = now

	filled := o
	filled.Status = domain.OrderStatusFilled
	filled.Price = fill
	filled.ExchangeID = "paper-" + o.ID
	filled.UpdatedMs = now

	evt := TradeLogEvent{
		OrderID:    filled.ID,
		Symbol:     o.Symbol,
		Side:       o.Side,
		Qty:        o.Qty,
		FillPrice:  fill,
		StopPrice:  o.StopPrice,
		TakeProfit: o.TakeProfit,
		Cash:       e.cash,
		RealizedPL: realizedDelta,
		TimestampMs: now,
	}
	select {
	case e.events <- evt:
	default:
		slog.WarnContext(ctx, "paper event channel full, dropping",
			"service", "paper",
			"mode", string(domain.ModePaper),
			"symbol", string(o.Symbol),
			"order_id", filled.ID,
		)
	}

	slog.InfoContext(ctx, "paper fill",
		"service", "paper",
		"mode", string(domain.ModePaper),
		"symbol", string(o.Symbol),
		"order_id", filled.ID,
		"side", string(o.Side),
		"qty", o.Qty.String(),
		"fill_price", fill.String(),
		"cash", e.cash.String(),
		"realized_delta", realizedDelta.String(),
	)

	return filled, nil
}

// CancelAllOrders is part of the runtime.Flattener contract. The paper
// engine fills synchronously in Place — it has no resting orders — so
// cancellation is a no-op.
func (e *Engine) CancelAllOrders(_ context.Context) error { return nil }

// FlattenPositions is part of the runtime.Flattener contract. It sells
// every open long position at the most recent bar close. Errors per-symbol
// are aggregated; the first one is returned so Kill can log it. All
// successful exits are committed regardless of any single failure.
func (e *Engine) FlattenPositions(ctx context.Context) error {
	e.mu.Lock()
	type sell struct {
		sym domain.Symbol
		qty decimal.Decimal
	}
	var work []sell
	for sym, p := range e.positions {
		if p.Qty.IsZero() {
			continue
		}
		work = append(work, sell{sym: sym, qty: p.Qty})
	}
	e.mu.Unlock()

	var firstErr error
	for _, w := range work {
		exit := domain.Order{
			ID:     "kill-" + string(w.sym),
			Symbol: w.sym,
			Side:   domain.SideSell,
			Type:   domain.OrderTypeMarket,
			Qty:    w.qty,
			Mode:   domain.ModePaper,
		}
		if _, err := e.Place(ctx, exit); err != nil {
			slog.ErrorContext(ctx, "paper flatten failed",
				"service", "paper",
				"symbol", string(w.sym),
				"err", err.Error(),
			)
			if firstErr == nil {
				firstErr = err
			}
		}
	}
	return firstErr
}

// CheckExits implements the runtime.ExitMonitor interface. It is called by
// the pipeline after each bar to enforce trailing-stop, hard-stop-loss, and
// take-profit exit conditions on every open position for the bar's symbol.
// Exits are executed as internal fills (identical accounting to Place) and
// their events are emitted on the trade-log channel for the UI.
func (e *Engine) CheckExits(ctx context.Context, b domain.Bar) ([]domain.Order, error) {
	e.mu.Lock()
	defer e.mu.Unlock()

	pos, ok := e.positions[b.Symbol]
	if !ok || pos.Qty.IsZero() {
		return nil, nil
	}

	price := b.Close
	var exitReason string
	switch {
	case pos.StopLoss.IsPositive() && price.LessThanOrEqual(pos.StopLoss):
		exitReason = "stop_loss"
	case pos.TakeProfit.IsPositive() && price.GreaterThanOrEqual(pos.TakeProfit):
		exitReason = "take_profit"
	}
	if exitReason == "" {
		return nil, nil
	}

	// Execute fill at bar close ± 1bp spread (sells fill below mid).
	bp := decimal.New(int64(spreadBps), -4)
	one := decimal.NewFromInt(1)
	fill := price.Mul(one.Sub(bp))

	qty := pos.Qty
	realizedDelta := fill.Sub(pos.AvgEntry).Mul(qty)
	e.totalRealizedPL = e.totalRealizedPL.Add(realizedDelta)
	pos.RealizedPL = pos.RealizedPL.Add(realizedDelta)
	pos.Qty = decimal.Zero
	pos.AvgEntry = decimal.Zero
	pos.UnrealizedPL = decimal.Zero
	pos.StopLoss = decimal.Zero
	pos.TakeProfit = decimal.Zero
	pos.TrailHigh = decimal.Zero
	e.cash = e.cash.Add(qty.Mul(fill))
	now := timex.NowMs()
	pos.UpdatedMs = now

	orderID := ids.New()
	evt := TradeLogEvent{
		OrderID:     orderID,
		Symbol:      b.Symbol,
		Side:        domain.SideSell,
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
		"qty", qty.String(),
		"fill_price", fill.String(),
		"realized_delta", realizedDelta.String(),
	)

	exitOrder := domain.Order{
		ID:         orderID,
		Symbol:     b.Symbol,
		Side:       domain.SideSell,
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
}

// Reset clears all positions and restores the initial balance. Existing event
// subscribers continue receiving on the same channel.
func (e *Engine) Reset() {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.cash = e.initial
	e.positions = make(map[domain.Symbol]*domain.Position)
	e.lastClose = make(map[domain.Symbol]decimal.Decimal)
	e.totalRealizedPL = decimal.Zero
	e.dayStartPL = decimal.Zero
	e.currentDayUTC = timex.NowMs() / 86_400_000
}
