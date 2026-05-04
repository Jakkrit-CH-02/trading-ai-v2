package builtin

import (
	"context"
	"errors"
	"fmt"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/ai"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

const AIName = "ai"

// AI is a strategy that delegates to the Python inference service.
// On any client error (timeout, breaker open, bad response) it falls back
// to HOLD with a reason — never propagates the error up the pipeline.
type AI struct {
	client      ai.Inferer
	interval    string
	minConfidence decimal.Decimal
}

func NewAI(client ai.Inferer, interval string, minConfidence decimal.Decimal) *AI {
	return &AI{client: client, interval: interval, minConfidence: minConfidence}
}

func (a *AI) Name() string { return AIName }

func (a *AI) OnBar(ctx context.Context, b domain.Bar) (strategy.Signal, error) {
	sig := strategy.Signal{
		ID:        ids.New(),
		Symbol:    b.Symbol,
		Action:    domain.SignalActionHold,
		Strategy:  AIName,
		CreatedMs: timex.NowMs(),
	}

	close, _ := b.Close.Float64()
	vol, _ := b.Volume.Float64()
	req := ai.InferenceRequest{
		Symbol:   string(b.Symbol),
		Interval: a.interval,
		Features: map[string]float64{
			"close":  close,
			"volume": vol,
		},
	}

	resp, err := a.client.Infer(ctx, req)
	if err != nil {
		if errors.Is(err, ai.ErrCircuitOpen) {
			sig.Reason = "ai unavailable: circuit open"
		} else {
			sig.Reason = fmt.Sprintf("ai unavailable: %v", err)
		}
		return sig, nil
	}

	conf := decimal.NewFromFloat(resp.Confidence)
	if conf.LessThan(a.minConfidence) {
		sig.Reason = fmt.Sprintf("ai confidence %s below threshold %s", conf.String(), a.minConfidence.String())
		return sig, nil
	}

	switch resp.Action {
	case "buy":
		sig.Action = domain.SignalActionBuy
	case "sell":
		sig.Action = domain.SignalActionSell
	default:
		sig.Action = domain.SignalActionHold
	}
	sig.Strength = conf
	sig.Reason = fmt.Sprintf("ai %s @ %s (model %s)", resp.Action, conf.String(), resp.ModelVersion)
	return sig, nil
}
