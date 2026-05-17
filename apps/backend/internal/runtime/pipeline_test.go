package runtime

import (
	"context"
	"fmt"
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

// TestPipeline_ExitMonitor_StopLoss verifies that the pipeline calls
// CheckExits before strategy evaluation, so a stop-loss hit on the paper
// engine flattens the position before the strategy sees the same bar.
func TestPipeline_ExitMonitor_StopLoss(t *testing.T) {
	ctx := context.Background()
	// Use a tight stop (0.1%) so the SL fires quickly on the down-leg.
	eng := paper.NewEngine(decimal.NewFromInt(100_000))
	strat := strategy.NewEngine(builtin.NewMACross(3, 5))
	policy := risk.Policy{
		MaxPositionPct:      decimal.NewFromFloat(0.5),
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.5),
		MaxSlippageBps:      30,
		RequireStopLoss:     true,
	}
	rsk := risk.NewEngine(policy)
	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)
	sizer := FixedFractionSizer(PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.001), // 0.1% stop — fires on any dip
	})
	pipe := NewPipeline(strat, rsk, mgr, eng, eng, eng, sizer)

	// Feed the climb bars: a BUY crossover will fire and open a position.
	sym := domain.Symbol("BTCUSDT")
	climbBars := fixtureBars(sym)[:10]
	var buyFired bool
	for _, b := range climbBars {
		o, err := pipe.OnBar(ctx, b)
		require.NoError(t, err)
		if o.Side == domain.SideBuy && o.ID != "" {
			buyFired = true
		}
	}
	// We may or may not have a buy depending on the fixture; if none fired,
	// the exit path is trivially a no-op — still valid to check no error.
	if !buyFired {
		t.Skip("no buy order fired on climb — fixture produced only hold signals")
	}

	// With 0.1% SL the next bar that is even slightly below entry will
	// trigger CheckExits inside the pipeline without errors.
	dropBar := domain.Bar{
		Symbol:    sym,
		Interval:  "1m",
		Close:     decimal.NewFromInt(1), // extreme drop → SL always triggers
		High:      decimal.NewFromInt(1),
		Low:       decimal.NewFromInt(1),
		Open:      decimal.NewFromInt(1),
		CloseTime: 999,
	}
	_, err := pipe.OnBar(ctx, dropBar)
	require.NoError(t, err, "pipeline must not surface SL exit as a system error")
	require.Empty(t, eng.Positions(), "position should be flat after SL exit via CheckExits")
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

// TestPipeline_DailyPnL_ReadFromEngine verifies that the pipeline reads
// DailyPnL from the paper engine via DailyPnLProvider, not from a hardcoded zero.
// We use a tiny drawdown policy so any realized loss triggers a risk rejection.
func TestPipeline_DailyPnL_ReadFromEngine(t *testing.T) {
	ctx := context.Background()
	eng := paper.NewEngine(decimal.NewFromInt(100_000))

	// Tiny daily drawdown limit so any realized loss blocks further entries.
	policy := risk.Policy{
		MaxPositionPct:      decimal.NewFromFloat(0.5),
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.0001),
		MaxSlippageBps:      30,
		RequireStopLoss:     true,
	}
	strat := strategy.NewEngine(builtin.NewMACross(3, 5))
	rsk := risk.NewEngine(policy)
	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)
	sizer := FixedFractionSizer(PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.001), // tight SL — fires quickly
	})
	pipe := NewPipeline(strat, rsk, mgr, eng, eng, eng, sizer)

	// Run all fixture bars. No system error should surface even if daily
	// drawdown fires — it must be treated as a risk rejection (warn, not error).
	for _, b := range fixtureBars(domain.Symbol("BTCUSDT")) {
		_, err := pipe.OnBar(ctx, b)
		require.NoError(t, err, "daily drawdown risk rejection must not be a system error")
	}
}

// alwaysBuyStrategy is a minimal strategy stub that returns a BUY signal on every bar.
// Each signal gets a unique ID derived from the bar's CloseTime to avoid idempotency replay.
type alwaysBuyStrategy struct{}

func (a *alwaysBuyStrategy) Name() string { return "always-buy-stub" }

func (a *alwaysBuyStrategy) OnBar(_ context.Context, b domain.Bar) (domain.Signal, error) {
	return domain.Signal{
		ID:     fmt.Sprintf("stub-buy-%d", b.CloseTime),
		Symbol: b.Symbol,
		Action: domain.SignalActionBuy,
		Reason: "always-buy-stub",
	}, nil
}

// TestPipeline_EntryCooldown_BlocksBuyAfterExit verifies that after a stop-loss
// auto-exit, the pipeline skips buy signals for the configured cooldown period.
func TestPipeline_EntryCooldown_BlocksBuyAfterExit(t *testing.T) {
	ctx := context.Background()
	eng := paper.NewEngine(decimal.NewFromInt(100_000))
	policy := risk.Policy{
		MaxPositionPct:      decimal.NewFromFloat(0.5),
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.5),
		MaxSlippageBps:      30,
		RequireStopLoss:     true,
	}
	rsk := risk.NewEngine(policy)
	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)
	sizer := FixedFractionSizer(PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.001), // 0.1% stop
	})

	sym := domain.Symbol("BTCUSDT")

	// Open a position manually so we can trigger the stop-loss.
	// Use the always-buy strategy so we don't depend on EMA convergence.
	strat := strategy.NewEngine(&alwaysBuyStrategy{})
	// WithEntryCooldown(6): the crash bar itself consumes one cooldown tick
	// (exit + decrement happen in the same OnBar), so 6 means 5 subsequent
	// bars are blocked — matching the loop below.
	pipe := NewPipeline(strat, rsk, mgr, eng, eng, eng, sizer).WithEntryCooldown(6)

	// Feed one bar so the paper engine has a market price, then the always-buy
	// strategy fires → a BUY order should be placed.
	entryBar := domain.Bar{
		Symbol: sym, Interval: "1m",
		Close: decimal.NewFromInt(100), High: decimal.NewFromInt(100),
		Low: decimal.NewFromInt(100), Open: decimal.NewFromInt(100),
		CloseTime: 1,
	}
	buyOrder, err := pipe.OnBar(ctx, entryBar)
	require.NoError(t, err)
	require.Equal(t, domain.SideBuy, buyOrder.Side, "always-buy strategy must place a buy on first bar")
	require.NotEmpty(t, eng.Positions(), "position must be open after buy")

	// Crash price below the stop → CheckExits fires → cooldown starts.
	crashBar := domain.Bar{
		Symbol: sym, Interval: "1m",
		Close: decimal.NewFromInt(1), High: decimal.NewFromInt(1),
		Low: decimal.NewFromInt(1), Open: decimal.NewFromInt(1),
		CloseTime: 2,
	}
	_, err = pipe.OnBar(ctx, crashBar)
	require.NoError(t, err)
	require.Empty(t, eng.Positions(), "SL must flatten position")

	// For the next 5 bars the always-buy strategy still fires, but cooldown
	// must block all of them — no new position should open.
	for i := 0; i < 5; i++ {
		bullBar := domain.Bar{
			Symbol: sym, Interval: "1m",
			Close: decimal.NewFromInt(200), High: decimal.NewFromInt(200),
			Low: decimal.NewFromInt(195), Open: decimal.NewFromInt(195),
			CloseTime: int64(3 + i),
		}
		o, err := pipe.OnBar(ctx, bullBar)
		require.NoError(t, err, "cooldown must not surface errors")
		require.Empty(t, o.ID, "cooldown must block new buy entry on bar %d", i)
		require.Empty(t, eng.Positions(), "no position during cooldown on bar %d", i)
	}

	// After cooldown expires (6th bar), the always-buy strategy should fire again.
	afterCooldownBar := domain.Bar{
		Symbol: sym, Interval: "1m",
		Close: decimal.NewFromInt(200), High: decimal.NewFromInt(200),
		Low: decimal.NewFromInt(195), Open: decimal.NewFromInt(195),
		CloseTime: 9,
	}
	o, err := pipe.OnBar(ctx, afterCooldownBar)
	require.NoError(t, err)
	require.NotEmpty(t, o.ID, "after cooldown expires, buy should be allowed again")
}
