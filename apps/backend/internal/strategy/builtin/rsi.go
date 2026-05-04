package builtin

import (
	"context"
	"fmt"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

const RSIName = "rsi"

// RSI strategy: BUY when RSI < oversold, SELL when RSI > overbought,
// HOLD otherwise. Uses Wilder's smoothing.
type RSI struct {
	period       int
	overbought   decimal.Decimal
	oversold     decimal.Decimal
	prevClose    decimal.Decimal
	avgGain      decimal.Decimal
	avgLoss      decimal.Decimal
	seenPrev     bool
	seedGains    []decimal.Decimal
	seedLosses   []decimal.Decimal
	ready        bool
}

func NewRSI(period int, oversold, overbought decimal.Decimal) *RSI {
	if period < 2 {
		period = 14
	}
	return &RSI{
		period:     period,
		oversold:   oversold,
		overbought: overbought,
	}
}

func (r *RSI) Name() string { return RSIName }

func (r *RSI) OnBar(_ context.Context, b domain.Bar) (strategy.Signal, error) {
	sig := strategy.Signal{
		ID:        ids.New(),
		Symbol:    b.Symbol,
		Action:    domain.SignalActionHold,
		Strategy:  RSIName,
		CreatedMs: timex.NowMs(),
	}

	if !r.seenPrev {
		r.prevClose = b.Close
		r.seenPrev = true
		sig.Reason = "warmup"
		return sig, nil
	}

	change := b.Close.Sub(r.prevClose)
	gain := decimal.Zero
	loss := decimal.Zero
	if change.IsPositive() {
		gain = change
	} else {
		loss = change.Neg()
	}
	r.prevClose = b.Close

	if !r.ready {
		r.seedGains = append(r.seedGains, gain)
		r.seedLosses = append(r.seedLosses, loss)
		if len(r.seedGains) < r.period {
			sig.Reason = "warmup"
			return sig, nil
		}
		sumG, sumL := decimal.Zero, decimal.Zero
		for i := range r.seedGains {
			sumG = sumG.Add(r.seedGains[i])
			sumL = sumL.Add(r.seedLosses[i])
		}
		p := decimal.NewFromInt(int64(r.period))
		r.avgGain = sumG.Div(p)
		r.avgLoss = sumL.Div(p)
		r.seedGains, r.seedLosses = nil, nil
		r.ready = true
	} else {
		p := decimal.NewFromInt(int64(r.period))
		pm1 := decimal.NewFromInt(int64(r.period - 1))
		r.avgGain = r.avgGain.Mul(pm1).Add(gain).Div(p)
		r.avgLoss = r.avgLoss.Mul(pm1).Add(loss).Div(p)
	}

	rsi := r.compute()
	switch {
	case rsi.LessThan(r.oversold):
		sig.Action = domain.SignalActionBuy
		sig.Reason = fmt.Sprintf("rsi %s < oversold %s", rsi.StringFixed(2), r.oversold.String())
		sig.Strength = r.oversold.Sub(rsi)
	case rsi.GreaterThan(r.overbought):
		sig.Action = domain.SignalActionSell
		sig.Reason = fmt.Sprintf("rsi %s > overbought %s", rsi.StringFixed(2), r.overbought.String())
		sig.Strength = rsi.Sub(r.overbought)
	default:
		sig.Reason = fmt.Sprintf("rsi %s in band", rsi.StringFixed(2))
	}
	return sig, nil
}

func (r *RSI) compute() decimal.Decimal {
	if r.avgLoss.IsZero() {
		return decimal.NewFromInt(100)
	}
	rs := r.avgGain.Div(r.avgLoss)
	hundred := decimal.NewFromInt(100)
	return hundred.Sub(hundred.Div(decimal.NewFromInt(1).Add(rs)))
}

// RSIFactory builds RSI from RuleConfig.
// Params: "period" (default 14), "oversold" (default 30), "overbought" (default 70).
func RSIFactory(cfg strategy.RuleConfig) (strategy.Strategy, error) {
	period, err := paramInt(cfg.Params, "period", 14)
	if err != nil {
		return nil, err
	}
	oversold, err := paramDecimal(cfg.Params, "oversold", decimal.NewFromInt(30))
	if err != nil {
		return nil, err
	}
	overbought, err := paramDecimal(cfg.Params, "overbought", decimal.NewFromInt(70))
	if err != nil {
		return nil, err
	}
	return NewRSI(period, oversold, overbought), nil
}

func paramDecimal(p map[string]string, key string, def decimal.Decimal) (decimal.Decimal, error) {
	v, ok := p[key]
	if !ok || v == "" {
		return def, nil
	}
	d, err := decimal.NewFromString(v)
	if err != nil {
		return decimal.Decimal{}, fmt.Errorf("param %q: %w", key, err)
	}
	return d, nil
}
