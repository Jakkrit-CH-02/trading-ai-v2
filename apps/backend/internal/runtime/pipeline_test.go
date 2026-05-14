package runtime

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/paper"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy/builtin"
)

// fixtureBars returns a deterministic price series for BTCUSDT that
// produces an MA-cross BUY then SELL when fed to a 3/5 EMA strategy.
//
// First the price climbs to force fast above slow, then it dives to flip
// fast below slow.
func fixtureBars(symbol domain.Symbol) []domain.Bar {
	prices := []int64{
		// climb (warmup + a buy crossover)
		100, 100, 100, 100, 100, // seed both EMAs equal
		120, 140, 160, 180, 200,
		// drop (sell crossover)
		180, 150, 120, 100, 90,
	}
	bars := make([]domain.Bar, 0, len(prices))
	for i, p := range prices {
		bars = append(bars, domain.Bar{
			Symbol:    symbol,
			Interval:  "1m",
			OpenTime:  int64(i),
			CloseTime: int64(i),
			Open:      decimal.NewFromInt(p),
			High:      decimal.NewFromInt(p),
			Low:       decimal.NewFromInt(p),
			Close:     decimal.NewFromInt(p),
			Volume:    decimal.NewFromInt(1),
		})
	}
	return bars
}

func newTestPipeline(t *testing.T) (*Pipeline, *paper.Engine) {
	t.Helper()
	eng := paper.NewEngine(decimal.NewFromInt(100_000))

	strat := strategy.NewEngine(builtin.NewMACross(3, 5))

	policy := risk.Policy{
		MaxPositionPct:      decimal.NewFromFloat(0.5), // generous for test
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.5),
		MaxSlippageBps:      30,
		RequireStopLoss:     true,
	}
	rsk := risk.NewEngine(policy)

	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)

	sizer := FixedFractionSizer(PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.05),
	})

	pipe := NewPipeline(strat, rsk, mgr, eng, eng, eng, sizer)
	return pipe, eng
}

func TestPipeline_FullFlow_BuyThenSell(t *testing.T) {
	ctx := context.Background()
	pipe, eng := newTestPipeline(t)
	bars := fixtureBars(domain.Symbol("BTCUSDT"))

	var orders []domain.Order
	for _, b := range bars {
		o, err := pipe.OnBar(ctx, b)
		require.NoErrorf(t, err, "bar @ ts %d close %s", b.CloseTime, b.Close)
		if o.ID != "" {
			orders = append(orders, o)
		}
	}

	require.GreaterOrEqual(t, len(orders), 2, "expected at least one buy and one sell")
	require.Equal(t, domain.SideBuy, orders[0].Side)
	require.Equal(t, domain.OrderStatusFilled, orders[0].Status)
	require.Equal(t, domain.ModePaper, orders[0].Mode)

	// At least one sell should have flipped the position back toward flat.
	sawSell := false
	for _, o := range orders[1:] {
		if o.Side == domain.SideSell {
			sawSell = true
			break
		}
	}
	require.True(t, sawSell, "expected a sell after the downward cross")

	// Pipeline should have recorded the last signal.
	require.NotEmpty(t, pipe.LastSignal().ID)

	// Equity should still be sane (we ran with a 10% fraction on a fake
	// price series; just assert it remained positive).
	require.True(t, eng.Equity().Sign() > 0)
}

func TestPipeline_RiskRejection_NotFatal(t *testing.T) {
	ctx := context.Background()

	eng := paper.NewEngine(decimal.NewFromInt(100_000))
	strat := strategy.NewEngine(builtin.NewMACross(3, 5))
	// Tiny position cap so any nonzero buy gets rejected.
	policy := risk.Policy{
		MaxPositionPct:      decimal.NewFromFloat(0.0001),
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.5),
		MaxSlippageBps:      30,
		RequireStopLoss:     true,
	}
	rsk := risk.NewEngine(policy)
	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)
	sizer := FixedFractionSizer(PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.05),
	})
	pipe := NewPipeline(strat, rsk, mgr, eng, eng, eng, sizer)

	for _, b := range fixtureBars(domain.Symbol("BTCUSDT")) {
		// Risk rejection must not surface as a system error.
		_, err := pipe.OnBar(ctx, b)
		require.NoError(t, err)
	}
}

func TestPipeline_Warm_PrimesLastSignalWithoutOrders(t *testing.T) {
	ctx := context.Background()
	pipe, eng := newTestPipeline(t)

	err := pipe.Warm(ctx, fixtureBars(domain.Symbol("BTCUSDT"))[:8])
	require.NoError(t, err)

	sig := pipe.LastSignal()
	require.NotEmpty(t, sig.ID, "warmup should record the latest strategy output")
	require.Equal(t, domain.Symbol("BTCUSDT"), sig.Symbol)
	require.True(t, eng.Equity().Equal(decimal.NewFromInt(100_000)), "warmup must not place historical orders")
	require.Empty(t, eng.Positions(), "warmup must not open positions")
}
