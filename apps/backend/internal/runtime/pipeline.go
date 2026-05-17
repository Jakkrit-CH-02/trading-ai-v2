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

// DailyPnLProvider returns the net realized P&L since the start of the current
// UTC day. Negative means a net loss today.
type DailyPnLProvider interface {
	DailyPnL() decimal.Decimal
}

// SizerResult holds everything the pipeline needs from the sizer: order
// quantities, initial stop-loss, take-profit, and trailing-stop parameters.
type SizerResult struct {
	Qty                decimal.Decimal
	StopLoss           decimal.Decimal
	TakeProfit         decimal.Decimal // zero = disabled
	TrailActivationPct decimal.Decimal // profit % at which trailing SL activates
	TrailPct           decimal.Decimal // trail distance below the highest price seen
	OK                 bool
}

// Sizer converts a strategy Signal + bar + account state into a SizerResult.
// Returning OK=false means the signal should be skipped (e.g. SELL with no position).
type Sizer func(sig domain.Signal, side domain.Side, bar domain.Bar, equity decimal.Decimal, positions []domain.Position) SizerResult

// PipelineConfig holds the static knobs of the pipeline.
type PipelineConfig struct {
	// PositionFraction is the fraction of equity to allocate to each new
	// long entry. Must be < risk.MaxPositionPct so the proposal passes.
	PositionFraction decimal.Decimal
	// StopLossFraction is the fractional drop from entry price used as the
	// hard floor stop (e.g. 0.02 = 2% below entry).
	StopLossFraction decimal.Decimal
	// TrailActivationPct is the profit % above entry at which the trailing
	// stop activates (e.g. 0.01 = 1%). Zero disables trailing.
	TrailActivationPct decimal.Decimal
	// TrailPct is the distance the stop trails below the highest price seen
	// once the trail is active (e.g. 0.015 = 1.5% below high).
	TrailPct decimal.Decimal
	// TakeProfitPct is the profit % at which a fixed TP exits the position
	// (e.g. 0.08 = 8%). Zero disables TP.
	TakeProfitPct decimal.Decimal
}

// FixedFractionSizer is the default sizer:
//   - BUY:  qty = floor((equity * PositionFraction) / price, 6 dp)
//           sl  = price * (1 - StopLossFraction)
//           tp  = price * (1 + TakeProfitPct) if TakeProfitPct > 0
//   - SELL: qty = current position qty for the symbol; ok=false if zero
//
// Stop loss for SELL is the bar close itself — the value is unused past the
// order manager but the risk engine still requires it non-zero.
func FixedFractionSizer(cfg PipelineConfig) Sizer {
	one := decimal.NewFromInt(1)
	return func(_ domain.Signal, side domain.Side, b domain.Bar, equity decimal.Decimal, positions []domain.Position) SizerResult {
		switch side {
		case domain.SideBuy:
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
			for _, p := range positions {
				if p.Symbol == b.Symbol && p.Qty.GreaterThan(decimal.Zero) {
					return SizerResult{Qty: p.Qty, StopLoss: b.Close, OK: true}
				}
			}
			return SizerResult{}
		default:
			return SizerResult{}
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

	mu               sync.Mutex
	lastSig          domain.Signal
	lastErr          error
	cooldownBars     int // configured cooldown length after any auto-exit
	cooldownBarsLeft int // decremented each OnBar; blocks buy signals while > 0
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

// WithEntryCooldown sets the number of bars to skip new buy entries after any
// auto-exit (stop-loss or take-profit). Zero disables cooldown.
func (p *Pipeline) WithEntryCooldown(bars int) *Pipeline {
	p.mu.Lock()
	p.cooldownBars = bars
	p.mu.Unlock()
	return p
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

// ExitMonitor is implemented by executors that enforce per-position stop-loss,
// take-profit, and trailing-stop conditions on every bar before strategy runs.
type ExitMonitor interface {
	CheckExits(ctx context.Context, b domain.Bar) ([]domain.Order, error)
}

// OnBar runs the full data → exits → strategy → risk → order chain on a single
// bar. Exit checks (SL/TP/trail) happen before strategy so the position is
// already flat if an exit fired. Returns the placed order on a successful
// strategy submit; a zero Order on hold or risk rejection.
func (p *Pipeline) OnBar(ctx context.Context, b domain.Bar) (domain.Order, error) {
	if p.sink != nil {
		p.sink.OnBar(b)
	}

	// Check trailing stop / take-profit exits before evaluating strategy.
	autoExited := false
	if em, ok := p.sink.(ExitMonitor); ok {
		if exits, err := em.CheckExits(ctx, b); err != nil {
			slog.WarnContext(ctx, "pipeline: exit check failed",
				"service", "runtime",
				"symbol", string(b.Symbol),
				"err", err.Error(),
			)
		} else {
			for _, o := range exits {
				autoExited = true
				slog.InfoContext(ctx, "pipeline: auto-exit executed",
					"service", "runtime",
					"symbol", string(b.Symbol),
					"order_id", o.ID,
					"side", string(o.Side),
					"price", o.Price.String(),
				)
			}
		}
	}

	// Start cooldown after any auto-exit (SL or TP).
	p.mu.Lock()
	if autoExited && p.cooldownBars > 0 {
		p.cooldownBarsLeft = p.cooldownBars
	}
	inCooldown := p.cooldownBarsLeft > 0
	cooldownRemaining := p.cooldownBarsLeft // capture BEFORE decrement
	if p.cooldownBarsLeft > 0 {
		p.cooldownBarsLeft--
	}
	p.mu.Unlock()

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

	// Skip new buy entries during cooldown.
	if inCooldown && side == domain.SideBuy {
		slog.InfoContext(ctx, "pipeline: buy skipped — entry cooldown active",
			"service", "runtime",
			"symbol", string(b.Symbol),
			"cooldown_bars_left", cooldownRemaining,
		)
		return domain.Order{}, nil
	}

	eq := p.equity.Equity()
	pos := p.positions.Positions()

	sized := p.sizer(sig, side, b, eq, pos)
	if !sized.OK {
		slog.InfoContext(ctx, "pipeline: signal skipped by sizer",
			"service", "runtime",
			"symbol", string(b.Symbol),
			"action", string(sig.Action),
			"signal_id", sig.ID,
		)
		return domain.Order{}, nil
	}

	// Read today's realized P&L if the equity provider implements DailyPnLProvider.
	dailyPnL := decimal.Zero
	if dp, ok := p.equity.(DailyPnLProvider); ok {
		dailyPnL = dp.DailyPnL()
	}

	prop := risk.Proposal{
		Signal:             sig,
		Side:               side,
		OrderType:          domain.OrderTypeMarket,
		Qty:                sized.Qty,
		Price:              b.Close,
		StopLoss:           sized.StopLoss,
		TakeProfit:         sized.TakeProfit,
		TrailActivationPct: sized.TrailActivationPct,
		TrailPct:           sized.TrailPct,
		Equity:             eq,
		DailyPnL:           dailyPnL,
		SlippageBps:        0,
	}

	vs, err := p.risk.Validate(ctx, prop)
	if err != nil {
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
