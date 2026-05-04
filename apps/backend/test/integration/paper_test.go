package integration

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/paper"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
)

// TestPaperEngine_FiveMixedSignals walks five buys/sells across two symbols
// through the order Manager into the paper Engine and asserts the resulting
// balance, open positions, and emitted trade-log events.
//
// Bookkeeping (1bp spread => buy@close*1.0001, sell@close*0.9999):
//   1. BUY  BTC 0.10 @ close 50000 -> fill 50005,    cash 10000.00 -> 4999.50
//   2. BUY  BTC 0.05 @ close 50000 -> fill 50005,    cash 4999.50 -> 2499.25  (BTC qty 0.15 avg 50005)
//   3. SELL BTC 0.10 @ close 52000 -> fill 51994.8,  cash 2499.25 -> 7698.73  (BTC qty 0.05)
//   4. BUY  ETH 1.00 @ close  3000 -> fill  3000.3,  cash 7698.73 -> 4698.43
//   5. SELL ETH 1.00 @ close  3100 -> fill  3099.69, cash 4698.43 -> 7798.12  (ETH closed)
//
// Final: cash 7798.12; one open position (BTC qty 0.05 avg 50005).
func TestPaperEngine_FiveMixedSignals(t *testing.T) {
	ctx := context.Background()

	eng := paper.NewEngine(decimal.NewFromInt(10_000))
	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)

	btc := domain.Symbol("BTCUSDT")
	eth := domain.Symbol("ETHUSDT")

	type step struct {
		sigID string
		bar   domain.Bar
		side  domain.Side
		qty   decimal.Decimal
	}
	steps := []step{
		{"s1", bar(btc, 50_000, 1), domain.SideBuy, decimal.NewFromFloat(0.10)},
		{"s2", bar(btc, 50_000, 2), domain.SideBuy, decimal.NewFromFloat(0.05)},
		{"s3", bar(btc, 52_000, 3), domain.SideSell, decimal.NewFromFloat(0.10)},
		{"s4", bar(eth, 3_000, 4), domain.SideBuy, decimal.NewFromInt(1)},
		{"s5", bar(eth, 3_100, 5), domain.SideSell, decimal.NewFromInt(1)},
	}

	for _, s := range steps {
		eng.OnBar(s.bar)

		action := domain.SignalActionBuy
		if s.side == domain.SideSell {
			action = domain.SignalActionSell
		}
		vs := risk.ValidatedSignal{
			Proposal: risk.Proposal{
				Signal: domain.Signal{
					ID:       s.sigID,
					Symbol:   s.bar.Symbol,
					Action:   action,
					Strategy: "test",
				},
				Side:      s.side,
				OrderType: domain.OrderTypeMarket,
				Qty:       s.qty,
				Price:     s.bar.Close,
				StopLoss:  s.bar.Close.Mul(decimal.NewFromFloat(0.95)),
				Equity:    decimal.NewFromInt(10_000),
			},
			ValidatedMs: s.bar.CloseTime,
		}

		placed, err := mgr.Submit(ctx, vs)
		require.NoErrorf(t, err, "submit %s", s.sigID)
		require.Equal(t, domain.OrderStatusFilled, placed.Status)
		require.Equal(t, domain.ModePaper, placed.Mode)
	}

	wantCash := decimal.RequireFromString("7798.12")
	gotCash := eng.Balance()
	require.Truef(t, wantCash.Equal(gotCash), "balance: want %s got %s", wantCash, gotCash)

	positions := eng.Positions()
	require.Len(t, positions, 1, "exactly one open position (BTC) — ETH closed out")

	p := positions[0]
	require.Equal(t, btc, p.Symbol)
	require.Truef(t, decimal.NewFromFloat(0.05).Equal(p.Qty), "btc qty: want 0.05 got %s", p.Qty)
	require.Truef(t, decimal.NewFromInt(50_005).Equal(p.AvgEntry), "btc avg: want 50005 got %s", p.AvgEntry)

	// Drain emitted events: should be exactly one per fill.
	var events []paper.TradeLogEvent
drain:
	for {
		select {
		case e := <-eng.Events():
			events = append(events, e)
		default:
			break drain
		}
	}
	require.Len(t, events, 5)
	require.Equal(t, btc, events[0].Symbol)
	require.Equal(t, domain.SideBuy, events[0].Side)
	require.Equal(t, eth, events[4].Symbol)
	require.Equal(t, domain.SideSell, events[4].Side)
	require.Truef(t, wantCash.Equal(events[4].Cash), "last event cash: want %s got %s", wantCash, events[4].Cash)
}

func bar(sym domain.Symbol, close int64, ts int64) domain.Bar {
	return domain.Bar{
		Symbol:    sym,
		Interval:  "1m",
		OpenTime:  ts,
		CloseTime: ts,
		Close:     decimal.NewFromInt(close),
	}
}
