package integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/paper"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/tradelog"
)

func TestTradeLog_RecordListSummary(t *testing.T) {
	ctx := context.Background()
	store := tradelog.NewMemoryStore()
	svc := tradelog.NewService(store)

	now := int64(1_700_000_000_000)
	sample := []tradelog.Record{
		{
			Mode: domain.ModePaper, Symbol: "BTCUSDT", Side: domain.SideBuy,
			OrderID: "o1", SignalID: "s1", Strategy: "ma-cross",
			Qty: decimal.NewFromFloat(0.1), FillPrice: decimal.NewFromInt(50_005),
			RealizedPL: decimal.Zero, TimestampMs: now,
		},
		{
			Mode: domain.ModePaper, Symbol: "BTCUSDT", Side: domain.SideSell,
			OrderID: "o2", SignalID: "s2", Strategy: "ma-cross",
			Qty: decimal.NewFromFloat(0.1), FillPrice: decimal.NewFromInt(52_000),
			RealizedPL: decimal.NewFromInt(199), TimestampMs: now + 60_000,
		},
		{
			Mode: domain.ModePaper, Symbol: "ETHUSDT", Side: domain.SideBuy,
			OrderID: "o3", SignalID: "s3", Strategy: "rsi",
			Qty: decimal.NewFromInt(1), FillPrice: decimal.NewFromInt(3_000),
			RealizedPL: decimal.Zero, TimestampMs: now + 120_000,
		},
		{
			Mode: domain.ModePaper, Symbol: "ETHUSDT", Side: domain.SideSell,
			OrderID: "o4", SignalID: "s4", Strategy: "rsi",
			Qty: decimal.NewFromInt(1), FillPrice: decimal.NewFromInt(2_900),
			RealizedPL: decimal.NewFromInt(-100), TimestampMs: now + 180_000,
		},
		{
			Mode: domain.ModeLive, Symbol: "BTCUSDT", Side: domain.SideBuy,
			OrderID: "o5", SignalID: "s5", Strategy: "ma-cross",
			Qty: decimal.NewFromFloat(0.05), FillPrice: decimal.NewFromInt(51_000),
			RealizedPL: decimal.Zero, TimestampMs: now + 240_000,
		},
	}
	for _, r := range sample {
		_, err := svc.Record(ctx, r)
		require.NoError(t, err)
	}

	t.Run("list all newest first", func(t *testing.T) {
		recs, total, err := svc.List(ctx, tradelog.Filter{Limit: 10})
		require.NoError(t, err)
		require.Equal(t, 5, total)
		require.Len(t, recs, 5)
		require.Equal(t, "o5", recs[0].OrderID)
		require.Equal(t, "o1", recs[4].OrderID)
	})

	t.Run("filter by symbol", func(t *testing.T) {
		recs, total, err := svc.List(ctx, tradelog.Filter{Symbol: "BTCUSDT", Limit: 10})
		require.NoError(t, err)
		require.Equal(t, 3, total)
		for _, r := range recs {
			require.Equal(t, domain.Symbol("BTCUSDT"), r.Symbol)
		}
	})

	t.Run("filter by mode", func(t *testing.T) {
		recs, total, err := svc.List(ctx, tradelog.Filter{Mode: domain.ModeLive, Limit: 10})
		require.NoError(t, err)
		require.Equal(t, 1, total)
		require.Len(t, recs, 1)
		require.Equal(t, "o5", recs[0].OrderID)
	})

	t.Run("filter by side+strategy", func(t *testing.T) {
		recs, total, err := svc.List(ctx, tradelog.Filter{
			Side: domain.SideSell, Strategy: "rsi", Limit: 10,
		})
		require.NoError(t, err)
		require.Equal(t, 1, total)
		require.Equal(t, "o4", recs[0].OrderID)
	})

	t.Run("filter by time range", func(t *testing.T) {
		recs, total, err := svc.List(ctx, tradelog.Filter{
			FromMs: now + 60_000, ToMs: now + 180_000, Limit: 10,
		})
		require.NoError(t, err)
		require.Equal(t, 3, total)
		require.Len(t, recs, 3)
	})

	t.Run("pagination", func(t *testing.T) {
		page1, total, err := svc.List(ctx, tradelog.Filter{Limit: 2, Offset: 0})
		require.NoError(t, err)
		require.Equal(t, 5, total)
		require.Len(t, page1, 2)
		require.Equal(t, "o5", page1[0].OrderID)
		require.Equal(t, "o4", page1[1].OrderID)

		page2, _, err := svc.List(ctx, tradelog.Filter{Limit: 2, Offset: 2})
		require.NoError(t, err)
		require.Len(t, page2, 2)
		require.Equal(t, "o3", page2[0].OrderID)
		require.Equal(t, "o2", page2[1].OrderID)

		page3, _, err := svc.List(ctx, tradelog.Filter{Limit: 2, Offset: 4})
		require.NoError(t, err)
		require.Len(t, page3, 1)
		require.Equal(t, "o1", page3[0].OrderID)

		page4, _, err := svc.List(ctx, tradelog.Filter{Limit: 2, Offset: 99})
		require.NoError(t, err)
		require.Empty(t, page4)
	})

	t.Run("summary all", func(t *testing.T) {
		sum, err := svc.Summary(ctx, tradelog.PeriodAll, now+1_000_000)
		require.NoError(t, err)
		require.Equal(t, 5, sum.Count)
		require.Equal(t, 3, sum.BuyCount)
		require.Equal(t, 2, sum.SellCount)
		require.Equal(t, 1, sum.WinningTrades)
		require.Equal(t, 1, sum.LosingTrades)
		// realized: +199 + -100 = 99
		require.Truef(t, decimal.NewFromInt(99).Equal(sum.RealizedPL),
			"realized_pl: want 99 got %s", sum.RealizedPL)
	})

	t.Run("summary day window excludes old", func(t *testing.T) {
		// "now" is 2 days past the newest record -> nothing in last 24h.
		sum, err := svc.Summary(ctx, tradelog.PeriodDay, now+2*24*60*60*1000)
		require.NoError(t, err)
		require.Equal(t, 0, sum.Count)
	})
}

func TestTradeLog_HTTPHandlers(t *testing.T) {
	ctx := context.Background()
	svc := tradelog.NewService(tradelog.NewMemoryStore())

	now := time.Now().UnixMilli()
	_, err := svc.Record(ctx, tradelog.Record{
		Mode: domain.ModePaper, Symbol: "BTCUSDT", Side: domain.SideBuy,
		OrderID: "o1", Qty: decimal.NewFromFloat(0.1), FillPrice: decimal.NewFromInt(50_000),
		TimestampMs: now,
	})
	require.NoError(t, err)
	_, err = svc.Record(ctx, tradelog.Record{
		Mode: domain.ModePaper, Symbol: "BTCUSDT", Side: domain.SideSell,
		OrderID: "o2", Qty: decimal.NewFromFloat(0.1), FillPrice: decimal.NewFromInt(51_000),
		RealizedPL: decimal.NewFromInt(100), TimestampMs: now + 1,
	})
	require.NoError(t, err)

	app := fiber.New()
	tradelog.RegisterRoutes(app, tradelog.NewHandler(svc))

	do := func(method, path string) *http.Response {
		req := httptest.NewRequest(method, path, nil)
		resp, err := app.Test(req, -1)
		require.NoError(t, err)
		return resp
	}

	t.Run("GET /api/trades", func(t *testing.T) {
		resp := do(http.MethodGet, "/api/trades?limit=10")
		require.Equal(t, http.StatusOK, resp.StatusCode)

		_, raw := decodeEnvelope(t, resp)
		require.JSONEq(t, `null`, string(raw["error"]))

		var data struct {
			Trades []tradelog.Record `json:"trades"`
			Total  int               `json:"total"`
			Limit  int               `json:"limit"`
		}
		require.NoError(t, json.Unmarshal(raw["data"], &data))
		require.Equal(t, 2, data.Total)
		require.Len(t, data.Trades, 2)
		require.Equal(t, "o2", data.Trades[0].OrderID, "newest first")
		require.Equal(t, "50000", data.Trades[1].FillPrice.String(), "money as string")
	})

	t.Run("GET /api/trades?symbol=BTCUSDT&side=buy", func(t *testing.T) {
		resp := do(http.MethodGet, "/api/trades?symbol=BTCUSDT&side=buy")
		require.Equal(t, http.StatusOK, resp.StatusCode)
		_, raw := decodeEnvelope(t, resp)
		var data struct {
			Trades []tradelog.Record `json:"trades"`
			Total  int               `json:"total"`
		}
		require.NoError(t, json.Unmarshal(raw["data"], &data))
		require.Equal(t, 1, data.Total)
		require.Equal(t, "o1", data.Trades[0].OrderID)
	})

	t.Run("GET /api/trades validation", func(t *testing.T) {
		resp := do(http.MethodGet, "/api/trades?limit=-1")
		require.Equal(t, http.StatusBadRequest, resp.StatusCode)
		env, _ := decodeEnvelope(t, resp)
		require.NotNil(t, env.Error)
		require.Equal(t, "validation_failed", env.Error.Code)
	})

	t.Run("GET /api/trades/summary", func(t *testing.T) {
		resp := do(http.MethodGet, "/api/trades/summary?period=all")
		require.Equal(t, http.StatusOK, resp.StatusCode)

		_, raw := decodeEnvelope(t, resp)
		var sum tradelog.Summary
		require.NoError(t, json.Unmarshal(raw["data"], &sum))
		require.Equal(t, tradelog.PeriodAll, sum.Period)
		require.Equal(t, 2, sum.Count)
		require.Equal(t, 1, sum.WinningTrades)
		require.Equal(t, "100", sum.RealizedPL.String())
	})

	t.Run("GET /api/trades/summary bad period", func(t *testing.T) {
		resp := do(http.MethodGet, "/api/trades/summary?period=bogus")
		require.Equal(t, http.StatusBadRequest, resp.StatusCode)
	})
}

// TestTradeLog_SubscribePaperEngine wires a paper.Engine through the order
// Manager and asserts the tradelog Service drains the engine's event channel
// and persists each fill as a Record.
func TestTradeLog_SubscribePaperEngine(t *testing.T) {
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()

	eng := paper.NewEngine(decimal.NewFromInt(10_000))
	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)

	svc := tradelog.NewService(tradelog.NewMemoryStore())
	done := make(chan struct{})
	go func() {
		svc.SubscribePaper(ctx, eng.Events())
		close(done)
	}()

	btc := domain.Symbol("BTCUSDT")
	steps := []struct {
		side  domain.Side
		qty   decimal.Decimal
		close int64
		sig   string
	}{
		{domain.SideBuy, decimal.NewFromFloat(0.1), 50_000, "sig-1"},
		{domain.SideSell, decimal.NewFromFloat(0.1), 52_000, "sig-2"},
	}
	for i, s := range steps {
		eng.OnBar(domain.Bar{Symbol: btc, Interval: "1m", OpenTime: int64(i + 1), CloseTime: int64(i + 1), Close: decimal.NewFromInt(s.close)})
		action := domain.SignalActionBuy
		if s.side == domain.SideSell {
			action = domain.SignalActionSell
		}
		vs := risk.ValidatedSignal{
			Proposal: risk.Proposal{
				Signal:    domain.Signal{ID: s.sig, Symbol: btc, Action: action, Strategy: "test"},
				Side:      s.side,
				OrderType: domain.OrderTypeMarket,
				Qty:       s.qty,
				Price:     decimal.NewFromInt(s.close),
				StopLoss:  decimal.NewFromInt(s.close - 1_000),
				Equity:    decimal.NewFromInt(10_000),
			},
			ValidatedMs: int64(i + 1),
		}
		_, err := mgr.Submit(ctx, vs)
		require.NoError(t, err)
	}

	// Poll until the subscriber has persisted both events (or fail after 1s).
	deadline := time.Now().Add(time.Second)
	var recs []tradelog.Record
	for time.Now().Before(deadline) {
		var total int
		var err error
		recs, total, err = svc.List(ctx, tradelog.Filter{Limit: 10})
		require.NoError(t, err)
		if total >= 2 {
			break
		}
		time.Sleep(10 * time.Millisecond)
	}
	require.Len(t, recs, 2, "tradelog persisted both paper fills")
	sides := map[domain.Side]bool{recs[0].Side: true, recs[1].Side: true}
	require.True(t, sides[domain.SideBuy] && sides[domain.SideSell], "both sides recorded")
	require.Equal(t, domain.ModePaper, recs[0].Mode)
	require.Equal(t, domain.ModePaper, recs[1].Mode)

	cancel()
	select {
	case <-done:
	case <-time.After(time.Second):
		t.Fatal("subscriber did not exit after ctx cancel")
	}
}
