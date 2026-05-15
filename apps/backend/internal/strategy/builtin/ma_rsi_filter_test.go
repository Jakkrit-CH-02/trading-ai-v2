package builtin

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

func TestMARSIFilter_Warmup(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	ctx := context.Background()
	for i := 0; i < 25; i++ {
		sig, err := f.OnBar(ctx, mkBar(100))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action,
			"bar %d should be Hold during warmup", i)
	}
}

// TestMARSIFilter_BuyBlocked_HighRSI: flat prices make avgLoss=0 → RSI=100.
// A cross-up fires but RSI (100) ≥ rsi_buy_max (60) → gate blocks.
func TestMARSIFilter_BuyBlocked_HighRSI(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	ctx := context.Background()

	for i := 0; i < 22; i++ {
		sig, err := f.OnBar(ctx, mkBar(100))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action)
	}

	// Bar 23 at 101: EMA9 crosses above EMA21, but RSI = 100 ≥ 60 → blocked
	sig, err := f.OnBar(ctx, mkBar(101))
	require.NoError(t, err)
	require.Equal(t, domain.SignalActionHold, sig.Action, "high RSI should block buy")
	require.Contains(t, sig.Reason, "rsi_gate_blocked")
}

// TestMARSIFilter_BuyAllowed: use 3 symmetric up/down cycles (100→115→100) to
// keep RSI ≈ 50 with EMA9 < EMA21 at rest, then 13 Hold bars of gradual +0.5
// rises followed by a final +0.5 bar that tips EMA9 above EMA21 with RSI ≈ 59 < 60.
func TestMARSIFilter_BuyAllowed(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	ctx := context.Background()

	// Warm-up: 3 symmetric cycles of 100→114 (15 bars up) then 114→100 (15 bars down).
	// Both EMAs converge near 100; EMA9 ends just below EMA21.
	for cycle := 0; cycle < 3; cycle++ {
		for i := 0; i < 15; i++ {
			_, err := f.OnBar(ctx, mkBar(100.0+float64(i)))
			require.NoError(t, err)
		}
		for i := 0; i < 15; i++ {
			_, err := f.OnBar(ctx, mkBar(115.0-float64(i)))
			require.NoError(t, err)
		}
	}

	// Steps 1–13: gradual +0.5 rise — no cross yet, all Hold.
	for i := 1; i <= 13; i++ {
		price := 100.0 + float64(i)*0.5
		sig, err := f.OnBar(ctx, mkBar(price))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action, "step %d (price=%.1f) should be Hold", i, price)
	}

	// Step 14 (price=107): EMA9 crosses above EMA21, RSI ≈ 59.67 < 60 → Buy allowed.
	sig, err := f.OnBar(ctx, mkBar(107.0))
	require.NoError(t, err)
	require.Equal(t, domain.SignalActionBuy, sig.Action)
	require.Contains(t, sig.Reason, "rsi")
}

// TestMARSIFilter_SellAllowed: 34 alternating 99/101 bars build RSI≈50 with EMAs
// near 100; the 34th bar (price=101) ends with EMA9 > EMA21 (buy cross). The
// next bar at 99 triggers EMA9 cross-below EMA21 with RSI≈48 > sell_min (40) → Sell emitted.
func TestMARSIFilter_SellAllowed(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	ctx := context.Background()

	// 34 alternating bars (0..33): odd indices → 101, even → 99.
	// Bar 33 (odd → 101) emits a buy cross, leaving EMA9 > EMA21.
	for i := 0; i < 34; i++ {
		price := 101.0
		if i%2 == 0 {
			price = 99.0
		}
		_, err := f.OnBar(ctx, mkBar(price))
		require.NoError(t, err)
	}

	// Bar at 99 (even-style drop): EMA9 crosses below EMA21, RSI≈48 > 40 → Sell allowed.
	sig, err := f.OnBar(ctx, mkBar(99))
	require.NoError(t, err)
	require.Equal(t, domain.SignalActionSell, sig.Action, "RSI > sell_min should allow sell")
	require.Contains(t, sig.Reason, "rsi")
}

// TestMARSIFilter_SellBlocked_LowRSI: 22 flat bars at 100 build RSI=100 with
// EMAs=100, then a sharp drop to 95 triggers EMA cross-down while RSI drops to 0
// (avgLoss dominates, avgGain=0) → RSI (0) ≤ sell_min (40) → gate blocks sell.
func TestMARSIFilter_SellBlocked_LowRSI(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	ctx := context.Background()

	// 22 flat bars at 100: RSI=100 (avgLoss=0), EMA9=EMA21=100.
	for i := 0; i < 22; i++ {
		sig, err := f.OnBar(ctx, mkBar(100))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action)
	}

	// Bar at 95: sharp drop → EMA9 crosses below EMA21, but RSI=0 ≤ 40 → blocked.
	sig, err := f.OnBar(ctx, mkBar(95))
	require.NoError(t, err)
	require.Equal(t, domain.SignalActionHold, sig.Action, "low RSI should block sell")
	require.Contains(t, sig.Reason, "rsi_gate_blocked")
}

func TestMARSIFilter_Name(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	require.Equal(t, "ma_rsi_filter", f.Name())
}

func TestMARSIFilterFactory_Defaults(t *testing.T) {
	strat, err := MARSIFilterFactory(strategy.RuleConfig{
		Name:    "ma_rsi_filter",
		Enabled: true,
		Params:  map[string]string{},
	})
	require.NoError(t, err)
	require.Equal(t, "ma_rsi_filter", strat.Name())
}
