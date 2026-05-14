package runtime

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

// MarketSink receives every bar before strategy evaluation. The paper engine
// is the canonical implementation: it uses the bar to mark positions and
// price subsequent fills.
type MarketSink interface {
	OnBar(b domain.Bar)
}

// EquityProvider returns the current account equity (cash + mark-to-market).
type EquityProvider interface {
	Equity() decimal.Decimal
}

// PositionProvider returns the current open positions snapshot. Used to size
// SELL orders to flatten existing exposure.
type PositionProvider interface {
	Positions() []domain.Position
}

// Sizer converts a strategy Signal + bar + account state into the (qty,
// stopLoss) pair carried on the risk Proposal. Returning ok=false means the
// signal should be skipped (e.g. SELL with no position).
type Sizer func(sig domain.Signal, side domain.Side, bar domain.Bar, equity decimal.Decimal, positions []domain.Position) (qty, stopLoss decimal.Decimal, ok bool)

// PipelineConfig holds the static knobs of the pipeline.
type PipelineConfig struct {
	// PositionFraction is the fraction of equity to allocate to each new
	// long entry. Must be < risk.MaxPositionPct so the proposal passes.
	PositionFraction decimal.Decimal
	// StopLossFraction is the fractional drop from entry price to use as
	// stop loss (e.g. 0.05 for a 5% stop).
	StopLossFraction decimal.Decimal
}

// FixedFractionSizer is the default sizer:
//   - BUY:  qty = floor((equity * PositionFraction) / price, 6 dp)
//   - SELL: qty = current position qty for the symbol; ok=false if zero
//
// Stop loss for BUY is price * (1 - StopLossFraction); for SELL we use the
// bar close itself as the stop (we are flattening, so the value is unused
// past the order manager but the risk engine still requires it non-zero).
func FixedFractionSizer(cfg PipelineConfig) Sizer {
	return func(_ domain.Signal, side domain.Side, b domain.Bar, equity decimal.Decimal, positions []domain.Position) (decimal.Decimal, decimal.Decimal, bool) {
		switch side {
		case domain.SideBuy:
			if equity.LessThanOrEqual(decimal.Zero) || b.Close.LessThanOrEqual(decimal.Zero) {
				return decimal.Zero, decimal.Zero, false
			}
			qty := equity.Mul(cfg.PositionFraction).Div(b.Close).Truncate(6)
			if qty.LessThanOrEqual(decimal.Zero) {
				return decimal.Zero, decimal.Zero, false
			}
			one := decimal.NewFromInt(1)
			sl := b.Close.Mul(one.Sub(cfg.StopLossFraction))
			return qty, sl, true
		case domain.SideSell:
			for _, p := range positions {
				if p.Symbol == b.Symbol && p.Qty.GreaterThan(decimal.Zero) {
					return p.Qty, b.Close, true
				}
			}
			return decimal.Zero, decimal.Zero, false
		default:
			return decimal.Zero, decimal.Zero, false
		}
	}
}

// Pipeline is the hot-path bar processor. One instance per running symbol.
type Pipeline struct {
	strategy  *strategy.Engine
	risk      *risk.Engine
	order     *order.Manager
	sink      MarketSink
	equity    EquityProvider
	positions PositionProvider
	sizer     Sizer

	mu      sync.Mutex
	lastSig domain.Signal
	lastErr error
}

// NewPipeline wires all pipeline stages. sink/equity/positions may be the
// same paper.Engine value.
func NewPipeline(
	strat *strategy.Engine,
	rsk *risk.Engine,
	mgr *order.Manager,
	sink MarketSink,
	eq EquityProvider,
	pos PositionProvider,
	sizer Sizer,
) *Pipeline {
	return &Pipeline{
		strategy:  strat,
		risk:      rsk,
		order:     mgr,
		sink:      sink,
		equity:    eq,
		positions: pos,
		sizer:     sizer,
	}
}

// Warm primes the market sink and strategy state from historical bars
// without sending signals into risk/order execution. This gives stateful
// strategies enough context to produce actionable signals immediately once
// live bars start arriving.
func (p *Pipeline) Warm(ctx context.Context, bars []domain.Bar) error {
	for _, b := range bars {
		if p.sink != nil {
			p.sink.OnBar(b)
		}
		sig, err := p.strategy.OnBar(ctx, b)
		if err != nil {
			p.recordErr(err)
			return fmt.Errorf("pipeline warm: strategy: %w", err)
		}
		p.recordSignal(sig)
	}
	return nil
}

// LastSignal returns the most recent signal seen by the pipeline (for
// status reporting). Zero-value if no bar processed yet.
func (p *Pipeline) LastSignal() domain.Signal {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.lastSig
}

// LastError returns the most recent system error from the pipeline.
func (p *Pipeline) LastError() error {
	p.mu.Lock()
	defer p.mu.Unlock()
	return p.lastErr
}

// OnBar runs the full data → strategy → risk → order chain on a single bar.
// Returns the placed order on a successful submit; a zero Order on hold or
// risk rejection. Risk rejections are logged at warn but not returned as
// errors — they are part of normal operation.
func (p *Pipeline) OnBar(ctx context.Context, b domain.Bar) (domain.Order, error) {
	if p.sink != nil {
		p.sink.OnBar(b)
	}

	sig, err := p.strategy.OnBar(ctx, b)
	if err != nil {
		p.recordErr(err)
		return domain.Order{}, fmt.Errorf("pipeline: strategy: %w", err)
	}
	p.recordSignal(sig)

	if sig.Action == domain.SignalActionHold {
		return domain.Order{}, nil
	}

	side := domain.SideBuy
	if sig.Action == domain.SignalActionSell {
		side = domain.SideSell
	}

	eq := p.equity.Equity()
	pos := p.positions.Positions()

	qty, sl, ok := p.sizer(sig, side, b, eq, pos)
	if !ok {
		slog.InfoContext(ctx, "pipeline: signal skipped by sizer",
			"service", "runtime",
			"symbol", string(b.Symbol),
			"action", string(sig.Action),
			"signal_id", sig.ID,
		)
		return domain.Order{}, nil
	}

	prop := risk.Proposal{
		Signal:      sig,
		Side:        side,
		OrderType:   domain.OrderTypeMarket,
		Qty:         qty,
		Price:       b.Close,
		StopLoss:    sl,
		Equity:      eq,
		DailyPnL:    decimal.Zero,
		SlippageBps: 0,
	}

	vs, err := p.risk.Validate(ctx, prop)
	if err != nil {
		// Risk rejections are expected and not system errors. Log at warn.
		slog.WarnContext(ctx, "pipeline: risk rejected",
			"service", "runtime",
			"symbol", string(b.Symbol),
			"action", string(sig.Action),
			"signal_id", sig.ID,
			"err", err.Error(),
		)
		if isRiskRejection(err) {
			return domain.Order{}, nil
		}
		p.recordErr(err)
		return domain.Order{}, fmt.Errorf("pipeline: risk: %w", err)
	}

	o, err := p.order.Submit(ctx, vs)
	if err != nil {
		p.recordErr(err)
		return domain.Order{}, fmt.Errorf("pipeline: order: %w", err)
	}
	return o, nil
}

func (p *Pipeline) recordSignal(s domain.Signal) {
	p.mu.Lock()
	p.lastSig = s
	p.mu.Unlock()
}

func (p *Pipeline) recordErr(e error) {
	p.mu.Lock()
	p.lastErr = e
	p.mu.Unlock()
}

func isRiskRejection(err error) bool {
	return errors.Is(err, risk.ErrPositionTooLarge) ||
		errors.Is(err, risk.ErrDailyDrawdown) ||
		errors.Is(err, risk.ErrStopLossRequired) ||
		errors.Is(err, risk.ErrSlippageExceeded)
}
