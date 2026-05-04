package order

import (
	"context"
	"fmt"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// Router selects the Executor for a given mode. Backtest hooks wire in later;
// live is gated until Sprint 7 via the liveDisabled executor.
type Router struct {
	paper    Executor
	live     Executor
	backtest Executor
}

func NewRouter(paper, live Executor) *Router {
	if live == nil {
		live = liveDisabled{}
	}
	return &Router{paper: paper, live: live}
}

// WithBacktest installs the backtest executor. Returns the same router for
// chained construction.
func (r *Router) WithBacktest(e Executor) *Router {
	r.backtest = e
	return r
}

func (r *Router) Route(mode domain.Mode) (Executor, error) {
	switch mode {
	case domain.ModePaper:
		if r.paper == nil {
			return nil, fmt.Errorf("paper: %w", ErrModeUnsupported)
		}
		return r.paper, nil
	case domain.ModeLive:
		return r.live, nil
	case domain.ModeBacktest:
		if r.backtest == nil {
			return nil, fmt.Errorf("backtest: %w", ErrModeUnsupported)
		}
		return r.backtest, nil
	default:
		return nil, fmt.Errorf("mode=%q: %w", mode, ErrUnknownMode)
	}
}

// liveDisabled is the placeholder live executor used until the live trading
// gate (risk check #5) and Binance order client land in Sprint 7.
type liveDisabled struct{}

func (liveDisabled) Place(_ context.Context, o domain.Order) (domain.Order, error) {
	return domain.Order{}, fmt.Errorf("symbol=%s: %w", o.Symbol, ErrLiveDisabled)
}
