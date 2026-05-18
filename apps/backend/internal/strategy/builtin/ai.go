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

// minWarmupBars is the minimum rolling window length before the strategy
// sends any inference request. Below this, EMA₂₆ and MACD signal produce
// NaN after feature dropna, so the Python service returns empty features.
const minWarmupBars = 34

// defaultMaxWindow is the maximum number of bars kept in the rolling window.
const defaultMaxWindow = 60

// AI is a strategy that delegates to the Python inference service.
// It maintains a rolling window of OHLCV bars and sends the full window to
// the service, letting Python compute all 14 features. During the warmup
// period (len(bars) < minWarmupBars) it returns HOLD without calling the
// service. On any client error (timeout, breaker open, bad response) it
// falls back to HOLD — never propagates the error up the pipeline.
type AI struct {
	client        ai.Inferer
	interval      string
	minConfidence decimal.Decimal
	maxWindow     int
	bars          []domain.Bar
}

func NewAI(client ai.Inferer, interval string, minConfidence decimal.Decimal) *AI {
	return &AI{
		client:        client,
		interval:      interval,
		minConfidence: minConfidence,
		maxWindow:     defaultMaxWindow,
	}
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

	// Maintain rolling window.
	a.bars = append(a.bars, b)
	if len(a.bars) > a.maxWindow {
		a.bars = a.bars[len(a.bars)-a.maxWindow:]
	}

	if len(a.bars) < minWarmupBars {
		sig.Reason = fmt.Sprintf("warmup: %d/%d bars", len(a.bars), minWarmupBars)
		return sig, nil
	}

	ohlcv := make([]ai.OHLCVBar, len(a.bars))
	for i, bar := range a.bars {
		c, _ := bar.Close.Float64()
		o, _ := bar.Open.Float64()
		h, _ := bar.High.Float64()
		l, _ := bar.Low.Float64()
		v, _ := bar.Volume.Float64()
		ohlcv[i] = ai.OHLCVBar{
			OpenTime: bar.OpenTime,
			Open:     o,
			High:     h,
			Low:      l,
			Close:    c,
			Volume:   v,
		}
	}

	req := ai.InferenceRequest{
		Symbol:   string(b.Symbol),
		Interval: a.interval,
		Bars:     ohlcv,
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
