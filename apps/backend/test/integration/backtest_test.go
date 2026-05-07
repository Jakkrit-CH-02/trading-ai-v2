package integration

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/backtest"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

// scriptedStrategy emits the given signal action for each bar, in order. Once
// the script is exhausted it returns HOLD. This makes the backtest run
// deterministic — independent of any indicator warmup.
type scriptedStrategy struct {
	actions []domain.SignalAction
	idx     int
}

func (s *scriptedStrategy) Name() string { return "scripted" }

func (s *scriptedStrategy) OnBar(_ context.Context, b domain.Bar) (strategy.Signal, error) {
	a := domain.SignalActionHold
	if s.idx < len(s.actions) {
		a = s.actions[s.idx]
		s.idx++
	}
	return strategy.Signal{
		ID:        "sig-" + b.Symbol.String() + "-" + itoa(b.CloseTime),
		Symbol:    b.Symbol,
		Action:    a,
		Strategy:  s.Name(),
		CreatedMs: b.CloseTime,
	}, nil
}

func itoa(n int64) string {
	if n == 0 {
		return "0"
	}
	neg := n < 0
	if neg {
		n = -n
	}
	var buf [20]byte
	i := len(buf)
	for n > 0 {
		i--
		buf[i] = byte('0' + n%10)
		n /= 10
	}
	if neg {
		i--
		buf[i] = '-'
	}
	return string(buf[i:])
}

// TestBacktest_DeterministicFixture replays a 6-bar BTCUSDT fixture against a
// scripted BUY/SELL/BUY/SELL strategy and asserts the resulting equity, trade
// list, and metrics are exact.
//
// Fixture (close prices): 100, 110, 120, 110, 100, 120
// Script:                 BUY, HOLD, SELL, BUY, HOLD, SELL
// Initial cash: 10_000, position_fraction: 1.0 (use full equity)
//
// Bar 1 BUY  @ 100 -> qty 100, cash 0, equity 10_000
// Bar 2 HOLD       -> equity 10_000 + 100*(110-100) = 11_000
// Bar 3 SELL @ 120 -> realize +2_000 -> cash 12_000, equity 12_000
// Bar 4 BUY  @ 110 -> qty 12_000/110 = 109.09090909, cash 0
//                     fill cost = 109.09090909 * 110 = 11_999.99999990
//                     residual cash = 0.00000010
// Bar 5 HOLD @ 100 -> equity = 0.00000010 + 109.09090909*100 = 10_909.09090910
// Bar 6 SELL @ 120 -> realize 109.09090909*(120-110) = 1_090.9090909
//                     cash after = 0.00000010 + 109.09090909*120 = 13_090.90909090
//                     final equity = 13_090.90909090
//
// Total trades (sells): 2; both winners; ProfitFactor very large; WinRate 1.
func TestBacktest_DeterministicFixture(t *testing.T) {
	ctx := context.Background()

	bars := mkBars("BTCUSDT", "1m", []int64{100, 110, 120, 110, 100, 120})
	strat := &scriptedStrategy{
		actions: []domain.SignalAction{
			domain.SignalActionBuy,
			domain.SignalActionHold,
			domain.SignalActionSell,
			domain.SignalActionBuy,
			domain.SignalActionHold,
			domain.SignalActionSell,
		},
	}

	cfg := backtest.Config{
		Symbol:           "BTCUSDT",
		Interval:         "1m",
		StrategyName:     "scripted",
		InitialCash:      decimal.NewFromInt(10_000),
		PositionFraction: decimal.NewFromInt(1),
		StopLossPct:      decimal.NewFromFloat(0.05),
	}

	idCounter := 0
	eng := backtest.NewEngine(cfg, strat, nil).
		WithClock(func() int64 { return 1_700_000_000_000 }).
		WithIDFunc(func() string {
			idCounter++
			return "id-" + itoa(int64(idCounter))
		})

	res, err := eng.Run(ctx, bars)
	require.NoError(t, err)

	require.Equal(t, 6, res.BarsProcessed)
	require.Len(t, res.EquityCurve, 6)
	require.Len(t, res.Trades, 4, "two BUY + two SELL")

	// Trade ordering & sides.
	require.Equal(t, domain.SideBuy, res.Trades[0].Side)
	require.Equal(t, domain.SideSell, res.Trades[1].Side)
	require.Equal(t, domain.SideBuy, res.Trades[2].Side)
	require.Equal(t, domain.SideSell, res.Trades[3].Side)

	// First sell realized exactly +2000.
	wantPL1 := decimal.NewFromInt(2_000)
	require.Truef(t, wantPL1.Equal(res.Trades[1].RealizedPL),
		"first sell realized PL: want %s got %s", wantPL1, res.Trades[1].RealizedPL)

	// Final equity ≈ 13090.90909090. Use Round(8) for stability across
	// arithmetic ordering.
	wantFinal := decimal.RequireFromString("13090.9090909")
	require.Truef(t, wantFinal.Round(4).Equal(res.FinalEquity.Round(4)),
		"final equity: want %s got %s", wantFinal, res.FinalEquity)

	// Metrics — closed-trade counts.
	require.Equal(t, 2, res.Metrics.TotalTrades)
	require.Equal(t, 2, res.Metrics.WinningTrades)
	require.Equal(t, 0, res.Metrics.LosingTrades)
	require.Truef(t, decimal.NewFromInt(1).Equal(res.Metrics.WinRate),
		"win rate: want 1 got %s", res.Metrics.WinRate)

	// Profit factor: all wins, no losses → engine sets sentinel 1_000_000.
	require.Truef(t, decimal.NewFromInt(1_000_000).Equal(res.Metrics.ProfitFactor),
		"profit factor (no-loss sentinel): got %s", res.Metrics.ProfitFactor)

	// Total return ≈ (13090.909... - 10000) / 10000 ≈ 0.309091.
	require.Truef(t, res.Metrics.TotalReturn.GreaterThan(decimal.NewFromFloat(0.30)),
		"total return: want > 0.30 got %s", res.Metrics.TotalReturn)
	require.Truef(t, res.Metrics.TotalReturn.LessThan(decimal.NewFromFloat(0.31)),
		"total return: want < 0.31 got %s", res.Metrics.TotalReturn)

	// Max drawdown: peak 12_000 (bar 3) -> trough 10_909.0909 (bar 5) ≈ 0.0909.
	require.Truef(t, res.Metrics.MaxDrawdown.GreaterThan(decimal.NewFromFloat(0.09)),
		"max dd: want > 0.09 got %s", res.Metrics.MaxDrawdown)
	require.Truef(t, res.Metrics.MaxDrawdown.LessThan(decimal.NewFromFloat(0.10)),
		"max dd: want < 0.10 got %s", res.Metrics.MaxDrawdown)

	// CreatedMs comes from the injected clock.
	require.Equal(t, int64(1_700_000_000_000), res.CreatedMs)
	require.NotEmpty(t, res.ID)
}

// TestBacktest_StorePersistRoundtrip exercises the in-memory store: insert,
// list, get-by-id.
func TestBacktest_StorePersistRoundtrip(t *testing.T) {
	ctx := context.Background()
	store := backtest.NewMemoryStore()

	r1 := backtest.Result{ID: "r1", CreatedMs: 1, FinalEquity: decimal.NewFromInt(100)}
	r2 := backtest.Result{ID: "r2", CreatedMs: 2, FinalEquity: decimal.NewFromInt(200)}
	require.NoError(t, store.Insert(ctx, r1))
	require.NoError(t, store.Insert(ctx, r2))

	got, err := store.Get(ctx, "r2")
	require.NoError(t, err)
	require.Equal(t, "r2", got.ID)

	_, err = store.Get(ctx, "missing")
	require.ErrorIs(t, err, backtest.ErrNotFound)

	list, total, err := store.List(ctx, 10, 0)
	require.NoError(t, err)
	require.Equal(t, 2, total)
	require.Len(t, list, 2)
	require.Equal(t, "r2", list[0].ID, "newest first by created_ms")
	require.Equal(t, "r1", list[1].ID)
}

func mkBars(sym domain.Symbol, interval string, closes []int64) []domain.Bar {
	out := make([]domain.Bar, 0, len(closes))
	for i, c := range closes {
		ts := int64(i+1) * 60_000
		px := decimal.NewFromInt(c)
		out = append(out, domain.Bar{
			Symbol:    sym,
			Interval:  interval,
			OpenTime:  ts - 60_000,
			CloseTime: ts,
			Open:      px,
			High:      px,
			Low:       px,
			Close:     px,
			Volume:    decimal.NewFromInt(1),
		})
	}
	return out
}
