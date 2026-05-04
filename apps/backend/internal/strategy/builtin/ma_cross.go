package builtin

import (
	"context"
	"fmt"
	"strconv"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

const MACrossName = "ma_cross"

// ema is a single exponential moving average. Seed = SMA over the first
// `period` values; subsequent values use the standard EMA recursion.
type ema struct {
	period int
	alpha  decimal.Decimal // 2 / (period + 1)
	oneMA  decimal.Decimal // 1 - alpha
	seed   []decimal.Decimal
	value  decimal.Decimal
	ready  bool
}

func newEMA(period int) *ema {
	a := decimal.NewFromInt(2).Div(decimal.NewFromInt(int64(period + 1)))
	return &ema{
		period: period,
		alpha:  a,
		oneMA:  decimal.NewFromInt(1).Sub(a),
		seed:   make([]decimal.Decimal, 0, period),
	}
}

func (e *ema) push(p decimal.Decimal) {
	if !e.ready {
		e.seed = append(e.seed, p)
		if len(e.seed) >= e.period {
			sum := decimal.Zero
			for _, s := range e.seed {
				sum = sum.Add(s)
			}
			e.value = sum.Div(decimal.NewFromInt(int64(e.period)))
			e.ready = true
			e.seed = nil
		}
		return
	}
	e.value = p.Mul(e.alpha).Add(e.value.Mul(e.oneMA))
}

// MACross emits BUY on a fast-over-slow EMA crossover and SELL on the inverse.
type MACross struct {
	fastP, slowP int
	fast, slow   *ema
	prevFast     decimal.Decimal
	prevSlow     decimal.Decimal
	havePrev     bool
}

func NewMACross(fast, slow int) *MACross {
	if fast >= slow {
		// Fast must be strictly shorter than slow; clamp defensively.
		fast, slow = 9, 21
	}
	return &MACross{
		fastP: fast,
		slowP: slow,
		fast:  newEMA(fast),
		slow:  newEMA(slow),
	}
}

func (m *MACross) Name() string { return MACrossName }

func (m *MACross) OnBar(_ context.Context, b domain.Bar) (strategy.Signal, error) {
	m.fast.push(b.Close)
	m.slow.push(b.Close)

	sig := strategy.Signal{
		ID:        ids.New(),
		Symbol:    b.Symbol,
		Action:    domain.SignalActionHold,
		Strategy:  MACrossName,
		CreatedMs: timex.NowMs(),
	}

	if !m.fast.ready || !m.slow.ready {
		sig.Reason = "warmup"
		return sig, nil
	}
	if !m.havePrev {
		m.prevFast = m.fast.value
		m.prevSlow = m.slow.value
		m.havePrev = true
		sig.Reason = "warmup: priming previous EMA"
		return sig, nil
	}

	f, s := m.fast.value, m.slow.value
	switch {
	case m.prevFast.LessThanOrEqual(m.prevSlow) && f.GreaterThan(s):
		sig.Action = domain.SignalActionBuy
		sig.Reason = fmt.Sprintf("ema%d crossed above ema%d", m.fastP, m.slowP)
		sig.Strength = f.Sub(s).Abs()
	case m.prevFast.GreaterThanOrEqual(m.prevSlow) && f.LessThan(s):
		sig.Action = domain.SignalActionSell
		sig.Reason = fmt.Sprintf("ema%d crossed below ema%d", m.fastP, m.slowP)
		sig.Strength = s.Sub(f).Abs()
	default:
		sig.Reason = "no cross"
	}
	m.prevFast, m.prevSlow = f, s
	return sig, nil
}

// MACrossFactory builds an MACross from a RuleConfig.
// Params: "fast" (int, default 9), "slow" (int, default 21).
func MACrossFactory(cfg strategy.RuleConfig) (strategy.Strategy, error) {
	fast, err := paramInt(cfg.Params, "fast", 9)
	if err != nil {
		return nil, err
	}
	slow, err := paramInt(cfg.Params, "slow", 21)
	if err != nil {
		return nil, err
	}
	return NewMACross(fast, slow), nil
}

func paramInt(p map[string]string, key string, def int) (int, error) {
	v, ok := p[key]
	if !ok || v == "" {
		return def, nil
	}
	n, err := strconv.Atoi(v)
	if err != nil {
		return 0, fmt.Errorf("param %q: %w", key, err)
	}
	return n, nil
}
