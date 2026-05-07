package paper

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
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
	Cash        decimal.Decimal `json:"cash"`
	RealizedPL  decimal.Decimal `json:"realized_pl"`
	TimestampMs int64           `json:"timestamp_ms"`
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
}

func NewEngine(initialCash decimal.Decimal) *Engine {
	return &Engine{
		cash:      initialCash,
		initial:   initialCash,
		positions: make(map[domain.Symbol]*domain.Position),
		lastClose: make(map[domain.Symbol]decimal.Decimal),
		events:    make(chan TradeLogEvent, eventBuffer),
	}
}

// Events returns the read end of the trade-log channel.
func (e *Engine) Events() <-chan TradeLogEvent { return e.events }

// OnBar feeds the latest bar so the engine can mark positions and price
// subsequent fills. Must be called at least once per symbol before Place.
func (e *Engine) OnBar(b domain.Bar) {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.lastClose[b.Symbol] = b.Close
	if p, ok := e.positions[b.Symbol]; ok && !p.Qty.IsZero() {
		p.UnrealizedPL = b.Close.Sub(p.AvgEntry).Mul(p.Qty)
		p.UpdatedMs = b.CloseTime
	}
}

// Balance returns the virtual cash balance.
func (e *Engine) Balance() decimal.Decimal {
	e.mu.Lock()
	defer e.mu.Unlock()
	return e.cash
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
		eq = eq.Add(p.Qty.Mul(px))
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
		cost := o.Qty.Mul(fill)
		if cost.GreaterThan(e.cash) {
			return domain.Order{}, fmt.Errorf("symbol=%s qty=%s cost=%s cash=%s: %w",
				o.Symbol, o.Qty.String(), cost.String(), e.cash.String(), ErrInsufficientCash)
		}
		newQty := pos.Qty.Add(o.Qty)
		// Weighted-average entry: ((avg * qty) + (fill * addQty)) / newQty.
		pos.AvgEntry = pos.AvgEntry.Mul(pos.Qty).Add(fill.Mul(o.Qty)).Div(newQty)
		pos.Qty = newQty
		e.cash = e.cash.Sub(cost)

	case domain.SideSell:
		if o.Qty.GreaterThan(pos.Qty) {
			return domain.Order{}, fmt.Errorf("symbol=%s qty=%s have=%s: %w",
				o.Symbol, o.Qty.String(), pos.Qty.String(), ErrInsufficientPosition)
		}
		realizedDelta = fill.Sub(pos.AvgEntry).Mul(o.Qty)
		pos.RealizedPL = pos.RealizedPL.Add(realizedDelta)
		pos.Qty = pos.Qty.Sub(o.Qty)
		e.cash = e.cash.Add(o.Qty.Mul(fill))
		if pos.Qty.IsZero() {
			pos.AvgEntry = decimal.Zero
		}
	}

	if !pos.Qty.IsZero() {
		pos.UnrealizedPL = mark.Sub(pos.AvgEntry).Mul(pos.Qty)
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
		OrderID:     filled.ID,
		Symbol:      o.Symbol,
		Side:        o.Side,
		Qty:         o.Qty,
		FillPrice:   fill,
		Cash:        e.cash,
		RealizedPL:  realizedDelta,
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

// Reset clears all positions and restores the initial balance. Existing event
// subscribers continue receiving on the same channel.
func (e *Engine) Reset() {
	e.mu.Lock()
	defer e.mu.Unlock()
	e.cash = e.initial
	e.positions = make(map[domain.Symbol]*domain.Position)
	e.lastClose = make(map[domain.Symbol]decimal.Decimal)
}
