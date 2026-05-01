package binance

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"
)

func newTestClient(t *testing.T, srv *httptest.Server) *Client {
	t.Helper()
	c := New(Config{
		APIKey:      "test-key",
		APISecret:   "test-secret",
		RestBaseURL: srv.URL,
	})
	// Tight limiter so tests stay fast.
	c.SetRateLimiter(NewTokenBucket(100, 1000))
	return c
}

func TestGetExchangeInfo_OK(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v3/exchangeInfo", r.URL.Path)
		w.WriteHeader(200)
		_ = json.NewEncoder(w).Encode(ExchangeInfo{
			Timezone:   "UTC",
			ServerTime: 1234,
			Symbols: []SymbolInfo{
				{Symbol: "BTCUSDT", Status: "TRADING", BaseAsset: "BTC", QuoteAsset: "USDT"},
			},
		})
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	out, err := c.GetExchangeInfo(context.Background())
	require.NoError(t, err)
	require.Len(t, out.Symbols, 1)
	require.Equal(t, "BTCUSDT", out.Symbols[0].Symbol)
}

func TestGetAccount_SignedHeadersAndQuery(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "test-key", r.Header.Get("X-MBX-APIKEY"))
		require.NotEmpty(t, r.URL.Query().Get("signature"))
		require.NotEmpty(t, r.URL.Query().Get("timestamp"))
		require.Equal(t, "5000", r.URL.Query().Get("recvWindow"))
		_ = json.NewEncoder(w).Encode(AccountInfo{
			CanTrade: true,
			Balances: []Balance{{Asset: "USDT", Free: decimal.NewFromInt(100), Locked: decimal.Zero}},
		})
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	out, err := c.GetAccount(context.Background())
	require.NoError(t, err)
	require.True(t, out.CanTrade)
	require.Len(t, out.Balances, 1)
}

func TestPlaceAndCancelOrder(t *testing.T) {
	var lastPath atomic.Value
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		lastPath.Store(r.Method + " " + r.URL.Path)
		_ = json.NewEncoder(w).Encode(OrderResponse{
			Symbol: "BTCUSDT", OrderID: 42, Status: "NEW",
		})
	}))
	defer srv.Close()

	c := newTestClient(t, srv)

	resp, err := c.PlaceOrder(context.Background(), OrderRequest{
		Symbol:   "BTCUSDT",
		Side:     "BUY",
		Type:     "MARKET",
		Quantity: decimal.NewFromFloat(0.001),
	})
	require.NoError(t, err)
	require.Equal(t, int64(42), resp.OrderID)
	require.Equal(t, "POST /api/v3/order", lastPath.Load())

	resp, err = c.CancelOrder(context.Background(), CancelRequest{Symbol: "BTCUSDT", OrderID: 42})
	require.NoError(t, err)
	require.Equal(t, "DELETE /api/v3/order", lastPath.Load())
}

func TestGetKlines_ParsesArray(t *testing.T) {
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v3/klines", r.URL.Path)
		require.Equal(t, "BTCUSDT", r.URL.Query().Get("symbol"))
		require.Equal(t, "1m", r.URL.Query().Get("interval"))
		// Each kline: [openTime, open, high, low, close, volume, closeTime, ...]
		_, _ = w.Write([]byte(`[
			[1700000000000,"100.0","110.0","90.0","105.0","12.5",1700000059999,"1300.0",10,"6.0","630.0","0"],
			[1700000060000,"105.0","112.0","101.0","108.0","9.0",1700000119999,"970.0",8,"4.0","430.0","0"]
		]`))
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	bars, err := c.GetKlines(context.Background(), KlinesQuery{Symbol: "BTCUSDT", Interval: "1m"})
	require.NoError(t, err)
	require.Len(t, bars, 2)
	require.Equal(t, domain.Symbol("BTCUSDT"), bars[0].Symbol)
	require.True(t, bars[0].Close.Equal(decimal.NewFromFloat(105)))
	require.Equal(t, int64(1700000000000), bars[0].OpenTime)
	require.Equal(t, int64(1700000059999), bars[0].CloseTime)
}

func TestRetry_On429ThenOK(t *testing.T) {
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		n := hits.Add(1)
		if n == 1 {
			w.WriteHeader(http.StatusTooManyRequests)
			_, _ = w.Write([]byte(`{"code":-1003,"msg":"too many"}`))
			return
		}
		_ = json.NewEncoder(w).Encode(ExchangeInfo{Timezone: "UTC"})
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	out, err := c.GetExchangeInfo(context.Background())
	require.NoError(t, err)
	require.Equal(t, "UTC", out.Timezone)
	require.GreaterOrEqual(t, hits.Load(), int32(2))
}

func TestRetry_On5xxExhausted(t *testing.T) {
	var hits atomic.Int32
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits.Add(1)
		w.WriteHeader(http.StatusBadGateway)
		_, _ = w.Write([]byte(`{"code":-1000,"msg":"oops"}`))
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	_, err := c.GetExchangeInfo(context.Background())
	require.Error(t, err)
	require.Equal(t, int32(3), hits.Load())
}

func TestSyncTime_SetsOffset(t *testing.T) {
	future := time.Now().UTC().Add(2 * time.Second).UnixMilli()
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		require.Equal(t, "/api/v3/time", r.URL.Path)
		_, _ = w.Write([]byte(`{"serverTime":` + intToStr(future) + `}`))
	}))
	defer srv.Close()

	c := newTestClient(t, srv)
	require.NoError(t, c.SyncTime(context.Background()))
	require.Greater(t, c.TimeOffsetMs(), int64(500))
}

func intToStr(i int64) string {
	const digits = "0123456789"
	if i == 0 {
		return "0"
	}
	neg := i < 0
	if neg {
		i = -i
	}
	var buf [20]byte
	pos := len(buf)
	for i > 0 {
		pos--
		buf[pos] = digits[i%10]
		i /= 10
	}
	if neg {
		pos--
		buf[pos] = '-'
	}
	return string(buf[pos:])
}

func TestTokenBucket_AllowAndWait(t *testing.T) {
	b := NewTokenBucket(2, 100) // 100 tps
	require.True(t, b.Allow(1))
	require.True(t, b.Allow(1))
	require.False(t, b.Allow(1))

	ctx, cancel := context.WithTimeout(context.Background(), 200*time.Millisecond)
	defer cancel()
	require.NoError(t, b.Wait(ctx, 1))
}

func TestSign_Deterministic(t *testing.T) {
	a := sign("secret", "a=1&b=2")
	b := sign("secret", "a=1&b=2")
	require.Equal(t, a, b)
	require.True(t, strings.HasPrefix(a, ""))
	require.Len(t, a, 64) // sha256 hex
}
