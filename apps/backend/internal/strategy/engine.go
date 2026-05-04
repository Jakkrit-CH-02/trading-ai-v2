package strategy

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
)

// Engine combines one or more Strategies. The first non-HOLD signal wins;
// if every strategy returns HOLD, a HOLD signal is emitted.
type Engine struct {
	strategies []Strategy
}

func NewEngine(strats ...Strategy) *Engine {
	return &Engine{strategies: strats}
}

func (e *Engine) Strategies() []Strategy { return e.strategies }

func (e *Engine) OnBar(ctx context.Context, bar domain.Bar) (Signal, error) {
	if len(e.strategies) == 0 {
		return holdSignal(bar, "engine", "no strategies configured"), nil
	}
	last := holdSignal(bar, "engine", "all strategies hold")
	for _, s := range e.strategies {
		sig, err := s.OnBar(ctx, bar)
		if err != nil {
			slog.WarnContext(ctx, "strategy error",
				"service", "strategy",
				"symbol", string(bar.Symbol),
				"strategy", s.Name(),
				"error", err.Error(),
			)
			return Signal{}, fmt.Errorf("strategy %s: %w", s.Name(), err)
		}
		if sig.Action != domain.SignalActionHold {
			return sig, nil
		}
		last = sig
	}
	return last, nil
}

func holdSignal(bar domain.Bar, strategy, reason string) Signal {
	return Signal{
		ID:        ids.New(),
		Symbol:    bar.Symbol,
		Action:    domain.SignalActionHold,
		Reason:    reason,
		Strategy:  strategy,
		CreatedMs: timex.NowMs(),
	}
}
