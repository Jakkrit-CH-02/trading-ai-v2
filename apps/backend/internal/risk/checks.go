package risk

import (
	"context"
	"fmt"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
)

// Engine is the pure risk validator. Construct once at startup with a Policy
// and call Validate per candidate order on the hot path.
type Engine struct {
	policy Policy
}

func NewEngine(p Policy) *Engine {
	return &Engine{policy: p}
}

// Validate runs checks #1-#4 from the risk policy in order. The first failing
// check returns its sentinel error wrapped with context; on success, returns a
// ValidatedSignal stamped with the current UTC ms.
//
// Live-mode gate (#5) and kill switch (#6) wire in Sprint 7.
func (e *Engine) Validate(_ context.Context, p Proposal) (ValidatedSignal, error) {
	if err := e.checkStopLoss(p); err != nil {
		return ValidatedSignal{}, err
	}
	if err := e.checkPositionSize(p); err != nil {
		return ValidatedSignal{}, err
	}
	if err := e.checkDailyDrawdown(p); err != nil {
		return ValidatedSignal{}, err
	}
	if err := e.checkSlippage(p); err != nil {
		return ValidatedSignal{}, err
	}

	return ValidatedSignal{
		Proposal:    p,
		ValidatedMs: timex.NowMs(),
	}, nil
}

func (e *Engine) checkStopLoss(p Proposal) error {
	if !e.policy.RequireStopLoss {
		return nil
	}
	if p.StopLoss.IsZero() || p.StopLoss.IsNegative() {
		return fmt.Errorf("symbol=%s: %w", p.Signal.Symbol, ErrStopLossRequired)
	}
	return nil
}

func (e *Engine) checkPositionSize(p Proposal) error {
	if p.Equity.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("symbol=%s equity<=0: %w", p.Signal.Symbol, ErrPositionTooLarge)
	}
	notional := p.Qty.Mul(p.Price).Abs()
	pct := notional.Div(p.Equity)
	if pct.GreaterThan(e.policy.MaxPositionPct) {
		return fmt.Errorf("symbol=%s notional_pct=%s max=%s: %w",
			p.Signal.Symbol, pct.String(), e.policy.MaxPositionPct.String(), ErrPositionTooLarge)
	}
	return nil
}

func (e *Engine) checkDailyDrawdown(p Proposal) error {
	if !p.DailyPnL.IsNegative() {
		return nil
	}
	if p.Equity.LessThanOrEqual(decimal.Zero) {
		return fmt.Errorf("symbol=%s equity<=0: %w", p.Signal.Symbol, ErrDailyDrawdown)
	}
	loss := p.DailyPnL.Abs()
	pct := loss.Div(p.Equity)
	if pct.GreaterThan(e.policy.MaxDailyDrawdownPct) {
		return fmt.Errorf("symbol=%s drawdown_pct=%s max=%s: %w",
			p.Signal.Symbol, pct.String(), e.policy.MaxDailyDrawdownPct.String(), ErrDailyDrawdown)
	}
	return nil
}

func (e *Engine) checkSlippage(p Proposal) error {
	if p.OrderType != domain.OrderTypeMarket {
		return nil
	}
	if p.SlippageBps > e.policy.MaxSlippageBps {
		return fmt.Errorf("symbol=%s slippage_bps=%d max=%d: %w",
			p.Signal.Symbol, p.SlippageBps, e.policy.MaxSlippageBps, ErrSlippageExceeded)
	}
	return nil
}
