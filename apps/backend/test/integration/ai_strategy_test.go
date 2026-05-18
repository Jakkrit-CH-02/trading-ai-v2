package integration

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/ai"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy/builtin"
)

func makeBTCBar(i int) domain.Bar {
	c := decimal.NewFromFloat(50000.0 + float64(i)*10)
	return domain.Bar{
		Symbol:   "BTCUSDT",
		Interval: "1m",
		OpenTime: int64(1_700_000_000_000 + i*60_000),
		Open:     c,
		High:     c.Add(decimal.NewFromFloat(100)),
		Low:      c.Sub(decimal.NewFromFloat(100)),
		Close:    c,
		Volume:   decimal.NewFromFloat(100.0),
	}
}

func TestAIStrategy_EndToEnd_BuySignal(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/v1/infer", r.URL.Path)

		var req ai.InferenceRequest
		require.NoError(t, json.NewDecoder(r.Body).Decode(&req))
		require.Equal(t, "BTCUSDT", req.Symbol)
		require.GreaterOrEqual(t, len(req.Bars), 34)

		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"data": map[string]interface{}{
				"action":        "buy",
				"confidence":    0.75,
				"model_version": "1",
			},
			"error": nil,
		})
	}))
	defer srv.Close()

	client := ai.New(ai.Config{BaseURL: srv.URL})
	strat := builtin.NewAI(client, "1m", decimal.NewFromFloat(0.5))
	ctx := context.Background()

	var lastSig domain.Signal
	for i := 0; i < 60; i++ {
		var err error
		lastSig, err = strat.OnBar(ctx, makeBTCBar(i))
		require.NoError(t, err)
	}

	require.Equal(t, domain.SignalActionBuy, lastSig.Action)
	require.True(t, lastSig.Strength.Equal(decimal.NewFromFloat(0.75)))
}
