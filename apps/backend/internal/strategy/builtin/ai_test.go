package builtin_test

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

func makeBar(i int) domain.Bar {
	c := decimal.NewFromFloat(100.0 + float64(i%5))
	return domain.Bar{
		Symbol:   "BTCUSDT",
		Interval: "1m",
		OpenTime: int64(1_700_000_000_000 + i*60_000),
		Open:     c.Sub(decimal.NewFromFloat(0.1)),
		High:     c.Add(decimal.NewFromFloat(0.5)),
		Low:      c.Sub(decimal.NewFromFloat(0.5)),
		Close:    c,
		Volume:   decimal.NewFromFloat(1000.0 + float64(i)),
	}
}

// TestAI_HoldDuringWarmup verifies that no HTTP call is made and HOLD is
// returned while the rolling window has fewer than 34 bars.
func TestAI_HoldDuringWarmup(t *testing.T) {
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		json.NewEncoder(w).Encode(ai.InferenceResponse{Action: "buy", Confidence: 0.9})
	}))
	defer srv.Close()

	client := ai.New(ai.Config{BaseURL: srv.URL})
	strat := builtin.NewAI(client, "1m", decimal.NewFromFloat(0.5))

	ctx := context.Background()
	for i := 0; i < 33; i++ {
		sig, err := strat.OnBar(ctx, makeBar(i))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action, "bar %d: expected HOLD during warmup", i)
	}
	require.Equal(t, 0, calls, "no HTTP calls expected during warmup")
}

// TestAI_CallsServiceAfterWarmup verifies an HTTP call is made on bar 34
// and the response action is forwarded.
func TestAI_CallsServiceAfterWarmup(t *testing.T) {
	calls := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		calls++
		var req ai.InferenceRequest
		require.NoError(t, json.NewDecoder(r.Body).Decode(&req))
		require.Equal(t, "BTCUSDT", req.Symbol)
		require.GreaterOrEqual(t, len(req.Bars), 34)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"data":  ai.InferenceResponse{Action: "buy", Confidence: 0.8, ModelVersion: "1"},
			"error": nil,
		})
	}))
	defer srv.Close()

	client := ai.New(ai.Config{BaseURL: srv.URL})
	strat := builtin.NewAI(client, "1m", decimal.NewFromFloat(0.5))

	ctx := context.Background()
	var lastSig domain.Signal
	var lastErr error
	for i := 0; i < 34; i++ {
		lastSig, lastErr = strat.OnBar(ctx, makeBar(i))
	}
	require.NoError(t, lastErr)
	require.Equal(t, 1, calls)
	require.Equal(t, domain.SignalActionBuy, lastSig.Action)
}

// TestAI_HoldOnLowConfidence checks that a response below min_confidence
// produces a HOLD.
func TestAI_HoldOnLowConfidence(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"data":  ai.InferenceResponse{Action: "buy", Confidence: 0.3, ModelVersion: "1"},
			"error": nil,
		})
	}))
	defer srv.Close()

	client := ai.New(ai.Config{BaseURL: srv.URL})
	// min_confidence = 0.6 — the 0.3 response must be filtered.
	strat := builtin.NewAI(client, "1m", decimal.NewFromFloat(0.6))

	ctx := context.Background()
	for i := 0; i < 34; i++ {
		strat.OnBar(ctx, makeBar(i)) //nolint:errcheck
	}
	// 35th bar — service returns buy with 0.3 confidence.
	sig, err := strat.OnBar(ctx, makeBar(34))
	require.NoError(t, err)
	require.Equal(t, domain.SignalActionHold, sig.Action)
}

// TestAI_WindowCappedAt60 verifies that the rolling window never grows
// beyond 60 bars (the max configured in NewAI default).
func TestAI_WindowCappedAt60(t *testing.T) {
	lastBarsCount := 0
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var req ai.InferenceRequest
		json.NewDecoder(r.Body).Decode(&req) //nolint:errcheck
		lastBarsCount = len(req.Bars)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]interface{}{
			"data":  ai.InferenceResponse{Action: "hold", Confidence: 0.5},
			"error": nil,
		})
	}))
	defer srv.Close()

	client := ai.New(ai.Config{BaseURL: srv.URL})
	strat := builtin.NewAI(client, "1m", decimal.NewFromFloat(0.0))

	ctx := context.Background()
	for i := 0; i < 100; i++ {
		strat.OnBar(ctx, makeBar(i)) //nolint:errcheck
	}
	require.LessOrEqual(t, lastBarsCount, 60, "window must not exceed 60 bars")
}
