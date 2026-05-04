package builtin

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

func mkBar(close float64) domain.Bar {
	return domain.Bar{
		Symbol:   domain.Symbol("BTCUSDT"),
		Interval: "1m",
		Close:    decimal.NewFromFloat(close),
		Open:     decimal.NewFromFloat(close),
		High:     decimal.NewFromFloat(close),
		Low:      decimal.NewFromFloat(close),
		Volume:   decimal.NewFromInt(1),
	}
}

// 30-bar fixture: 21 flat at 100 (warmup + seed), then 9 bars at 110
// to force EMA9 to cross above EMA21.
func crossUpFixture() []domain.Bar {
	bars := make([]domain.Bar, 0, 30)
	for i := 0; i < 21; i++ {
		bars = append(bars, mkBar(100))
	}
	for i := 0; i < 9; i++ {
		bars = append(bars, mkBar(110))
	}
	return bars
}

func TestMaCross_Warmup(t *testing.T) {
	s := NewMACross(9, 21)
	ctx := context.Background()
	for i := 0; i < 20; i++ {
		sig, err := s.OnBar(ctx, mkBar(100))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action,
			"bar %d should be HOLD during warmup", i)
	}
}

func TestMaCross_NoCross_FlatPrices(t *testing.T) {
	s := NewMACross(9, 21)
	ctx := context.Background()
	for i := 0; i < 30; i++ {
		sig, err := s.OnBar(ctx, mkBar(100))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action,
			"bar %d should be HOLD with flat prices", i)
	}
}

func TestMaCross_CrossUp(t *testing.T) {
	s := NewMACross(9, 21)
	ctx := context.Background()
	bars := crossUpFixture()

	var sawBuy bool
	for i, b := range bars {
		sig, err := s.OnBar(ctx, b)
		require.NoError(t, err)
		if sig.Action == domain.SignalActionBuy {
			require.GreaterOrEqual(t, i, 21,
				"buy must happen after warmup (got at bar %d)", i)
			require.NotEmpty(t, sig.Reason)
			sawBuy = true
			break
		}
		require.NotEqual(t, domain.SignalActionSell, sig.Action,
			"unexpected SELL at bar %d", i)
	}
	require.True(t, sawBuy, "expected a BUY cross-up signal")
}

func TestMaCross_CrossDown(t *testing.T) {
	s := NewMACross(9, 21)
	ctx := context.Background()

	// Rising prices establish EMA9 > EMA21.
	for i := 0; i < 21; i++ {
		_, err := s.OnBar(ctx, mkBar(100+float64(i)))
		require.NoError(t, err)
	}
	// Sharp drop should produce a cross-down.
	var sawSell bool
	for i := 0; i < 20; i++ {
		sig, err := s.OnBar(ctx, mkBar(50))
		require.NoError(t, err)
		if sig.Action == domain.SignalActionSell {
			require.NotEmpty(t, sig.Reason)
			sawSell = true
			break
		}
	}
	require.True(t, sawSell, "expected a SELL cross-down signal")
}

func TestEMA_Correctness(t *testing.T) {
	// period=3 → alpha = 2/(3+1) = 0.5
	// SMA seed at bar 3, then EMA = 0.5*price + 0.5*prev
	e := newEMA(3)
	type tc struct {
		price float64
		ready bool
		value float64 // only checked when ready
	}
	cases := []tc{
		{10, false, 0},
		{11, false, 0},
		{12, true, 11},   // SMA(10,11,12)
		{13, true, 12},   // 0.5*13 + 0.5*11
		{14, true, 13},   // 0.5*14 + 0.5*12
		{15, true, 14},   // 0.5*15 + 0.5*13
	}
	for i, c := range cases {
		e.push(decimal.NewFromFloat(c.price))
		require.Equal(t, c.ready, e.ready, "bar %d ready", i)
		if c.ready {
			require.True(t,
				e.value.Equal(decimal.NewFromFloat(c.value)),
				"bar %d EMA value: got %s want %v", i, e.value, c.value)
		}
	}
}
