package backtest

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy/builtin"
)

// scriptedStrategy replays a fixed sequence of signals, one per bar.
type scriptedStrategy struct {
	actions []domain.SignalAction
	idx     int
}

func (s *scriptedStrategy) Name() string { return "scripted" }

func (s *scriptedStrategy) OnBar(_ context.Context, _ domain.Bar) (strategy.Signal, error) {
	action := domain.SignalActionHold
	if s.idx < len(s.actions) {
		action = s.actions[s.idx]
	}
	s.idx++
	return strategy.Signal{ID: "sig", Action: action}, nil
}

func bar(closePrice, lowPrice float64, t int64) domain.Bar {
	return domain.Bar{
		Symbol:    "BTCUSDT",
		Interval:  "1h",
		OpenTime:  t,
		CloseTime: t + 1,
		Open:      decimal.NewFromFloat(closePrice),
		High:      decimal.NewFromFloat(closePrice),
		Low:       decimal.NewFromFloat(lowPrice),
		Close:     decimal.NewFromFloat(closePrice),
		Volume:    decimal.NewFromInt(1),
	}
}

// TestEngine_StopLoss_TriggersExit verifies that when price falls below the
// computed stop price the position is closed before the next signal fires.
func TestEngine_StopLoss_TriggersExit(t *testing.T) {
	// Entry at 100, SL 10% → stop at 90.
	// Bar 0: BUY at close=100, low=100  → enters position
	// Bar 1: low=89 (< 90)              → stop-loss fill at 90
	// Bar 2: SELL signal                → no position, ignored
	strat := &scriptedStrategy{actions: []domain.SignalAction{
		domain.SignalActionBuy,
		domain.SignalActionHold,
		domain.SignalActionSell,
	}}
	cfg := Config{
		Symbol:           "BTCUSDT",
		Interval:         "1h",
		InitialCash:      decimal.NewFromInt(10_000),
		PositionFraction: decimal.NewFromFloat(1.0), // full equity for easy math
		StopLossPct:      decimal.NewFromFloat(0.10),
	}
	bars := []domain.Bar{
		bar(100, 100, 1000),
		bar(89, 89, 2000),
		bar(89, 89, 3000),
	}
	res, err := NewEngine(cfg, strat, nil).WithIDFunc(func() string { return "id" }).Run(context.Background(), bars)
	require.NoError(t, err)

	// Should have 1 buy + 1 stop-loss sell = 2 trades
	require.Len(t, res.Trades, 2)
	sell := res.Trades[1]
	require.Equal(t, domain.SideSell, sell.Side)
	require.Equal(t, "stop_loss", sell.Reason)
	require.Equal(t, "90", sell.Price.String())

	// realized P/L = (90-100) * qty; qty = 10000/100 = 100 → loss of 1000
	require.True(t, sell.RealizedPL.IsNegative())
}

// TestEngine_TrailingStop_AdvancesOnProfit verifies that once price exceeds the
// activation threshold the stop trails up and triggers on a pullback.
func TestEngine_TrailingStop_AdvancesOnProfit(t *testing.T) {
	// Entry 100, SL 10% (stop=90), trail activates at 1% profit (>101),
	// trails 5% below high.
	// Bar 0: BUY  close=100 low=100  → stopPrice=90, trailHigh=100
	// Bar 1: HOLD close=105 low=104  → >101, trailHigh=105, newSL=105*0.95=99.75 > 90
	// Bar 2: HOLD close=90  low=89   → low=89 <= 99.75 → stop_loss at 99.75
	strat := &scriptedStrategy{actions: []domain.SignalAction{
		domain.SignalActionBuy,
		domain.SignalActionHold,
		domain.SignalActionHold,
	}}
	cfg := Config{
		Symbol:             "BTCUSDT",
		Interval:           "1h",
		InitialCash:        decimal.NewFromInt(10_000),
		PositionFraction:   decimal.NewFromFloat(1.0),
		StopLossPct:        decimal.NewFromFloat(0.10),
		TrailActivationPct: decimal.NewFromFloat(0.01),
		TrailPct:           decimal.NewFromFloat(0.05),
	}
	bars := []domain.Bar{
		bar(100, 100, 1000),
		bar(105, 104, 2000),
		bar(90, 89, 3000),
	}
	res, err := NewEngine(cfg, strat, nil).WithIDFunc(func() string { return "id" }).Run(context.Background(), bars)
	require.NoError(t, err)
	require.Len(t, res.Trades, 2)
	sell := res.Trades[1]
	require.Equal(t, "stop_loss", sell.Reason)
	require.Equal(t, "99.75", sell.Price.String())
}

// TestEngine_TrailingStop_NoTrailWhenDisabled verifies that zero TrailPct
// leaves the stop fixed and does not trigger on a dip that stays above the
// original stop.
func TestEngine_TrailingStop_NoTrailWhenDisabled(t *testing.T) {
	strat := &scriptedStrategy{actions: []domain.SignalAction{
		domain.SignalActionBuy,
		domain.SignalActionHold,
		domain.SignalActionHold,
	}}
	cfg := Config{
		Symbol:           "BTCUSDT",
		Interval:         "1h",
		InitialCash:      decimal.NewFromInt(10_000),
		PositionFraction: decimal.NewFromFloat(1.0),
		StopLossPct:      decimal.NewFromFloat(0.10), // stop at 90
		TrailPct:         decimal.Zero,               // trailing disabled
	}
	bars := []domain.Bar{
		bar(100, 100, 1000), // entry
		bar(105, 104, 2000), // price rises; no trail
		bar(92, 91, 3000),   // low=91 > 90 — NOT stopped out
	}
	res, err := NewEngine(cfg, strat, nil).WithIDFunc(func() string { return "id" }).Run(context.Background(), bars)
	require.NoError(t, err)
	require.Len(t, res.Trades, 1) // only the BUY; still open
	require.Equal(t, domain.SideBuy, res.Trades[0].Side)
}

// TestEngine_StopLoss_NoTrigger verifies that a price dip that stays above the
// stop does NOT close the position.
func TestEngine_StopLoss_NoTrigger(t *testing.T) {
	// Entry at 100, SL 10% → stop at 90.
	// Bar 1: low=91 (> 90) → no stop hit
	// Bar 2: SELL signal   → normal close
	strat := &scriptedStrategy{actions: []domain.SignalAction{
		domain.SignalActionBuy,
		domain.SignalActionHold,
		domain.SignalActionSell,
	}}
	cfg := Config{
		Symbol:           "BTCUSDT",
		Interval:         "1h",
		InitialCash:      decimal.NewFromInt(10_000),
		PositionFraction: decimal.NewFromFloat(1.0),
		StopLossPct:      decimal.NewFromFloat(0.10),
	}
	bars := []domain.Bar{
		bar(100, 100, 1000),
		bar(95, 91, 2000),
		bar(105, 104, 3000),
	}
	res, err := NewEngine(cfg, strat, nil).WithIDFunc(func() string { return "id" }).Run(context.Background(), bars)
	require.NoError(t, err)

	require.Len(t, res.Trades, 2)
	sell := res.Trades[1]
	require.NotEqual(t, "stop_loss", sell.Reason) // closed by strategy, not stop
}

// testBar builds a domain.Bar for use in take-profit and other tests that need
// a symbol parameter. The existing bar() helper hard-codes "BTCUSDT".
func testBar(symbol string, closePrice, lowPrice float64, t int64) domain.Bar {
	return domain.Bar{
		Symbol:    domain.Symbol(symbol),
		Interval:  "1m",
		OpenTime:  t,
		CloseTime: t + 1,
		Open:      decimal.NewFromFloat(closePrice),
		High:      decimal.NewFromFloat(closePrice),
		Low:       decimal.NewFromFloat(lowPrice),
		Close:     decimal.NewFromFloat(closePrice),
		Volume:    decimal.NewFromInt(1),
	}
}

func TestEngine_TakeProfit_ExitsAtTarget(t *testing.T) {
	ctx := context.Background()

	// Price: flat seed → BUY crossover → rises past 6% TP → strategy would hold
	// The TP check must fire before the strategy's SELL signal matters.
	bars := []domain.Bar{
		testBar("BTCUSDT", 100, 95, 1),
		testBar("BTCUSDT", 100, 95, 2),
		testBar("BTCUSDT", 100, 95, 3),
		testBar("BTCUSDT", 120, 95, 4), // fast EMA spikes → BUY signal; entry ~120
		testBar("BTCUSDT", 125, 120, 5),
		testBar("BTCUSDT", 128, 122, 6), // 128 > 120 * 1.06 = 127.2 → TP fires
		testBar("BTCUSDT", 200, 125, 7), // would be bigger win if TP not capping
	}

	cfg := Config{
		Symbol:           "BTCUSDT",
		Interval:         "1m",
		StrategyName:     "ma_cross",
		InitialCash:      decimal.NewFromInt(10_000),
		PositionFraction: decimal.NewFromFloat(0.5),
		StopLossPct:      decimal.NewFromFloat(0.20), // wide SL so only TP fires
		TakeProfitPct:    decimal.NewFromFloat(0.06),
	}

	strat := builtin.NewMACross(2, 3)
	eng := NewEngine(cfg, strat, nil)
	eng.WithIDFunc(func() string { return "test-id" })

	res, err := eng.Run(ctx, bars)
	require.NoError(t, err)

	var foundTP bool
	for _, tr := range res.Trades {
		if tr.Reason == "take_profit" {
			foundTP = true
		}
	}
	require.True(t, foundTP, "expected at least one take_profit exit, got trades: %+v", res.Trades)
}
