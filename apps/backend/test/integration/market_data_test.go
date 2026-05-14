package integration

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sort"
	"sync"
	"testing"
	"time"

	"github.com/gofiber/fiber/v2"
	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/api/handlers"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data/collector"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data/market"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// fakeCache and fakeRepo implement data.Cache and data.Repo against
// in-memory state. They exercise the same code paths the Redis/Postgres
// implementations would; only the storage substrate differs.

type fakeCache struct {
	mu   sync.Mutex
	bars map[string]domain.Bar
}

func newFakeCache() *fakeCache { return &fakeCache{bars: map[string]domain.Bar{}} }

func ckey(sym domain.Symbol, interval string) string {
	return string(sym) + "|" + interval
}

func (c *fakeCache) SetLatestBar(_ context.Context, b domain.Bar) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	c.bars[ckey(b.Symbol, b.Interval)] = b
	return nil
}

func (c *fakeCache) GetLatestBar(_ context.Context, sym domain.Symbol, interval string) (domain.Bar, error) {
	c.mu.Lock()
	defer c.mu.Unlock()
	b, ok := c.bars[ckey(sym, interval)]
	if !ok {
		return domain.Bar{}, data.ErrNotFound
	}
	return b, nil
}

type fakeRepo struct {
	mu   sync.Mutex
	bars map[string][]domain.Bar // key = ckey(symbol, interval)
}

func newFakeRepo() *fakeRepo { return &fakeRepo{bars: map[string][]domain.Bar{}} }

func (r *fakeRepo) InsertBars(_ context.Context, bars []domain.Bar) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	for _, b := range bars {
		k := ckey(b.Symbol, b.Interval)
		// dedupe by open_time (mirrors ON CONFLICT DO NOTHING)
		dup := false
		for _, existing := range r.bars[k] {
			if existing.OpenTime == b.OpenTime {
				dup = true
				break
			}
		}
		if dup {
			continue
		}
		r.bars[k] = append(r.bars[k], b)
	}
	return nil
}

func (r *fakeRepo) sortedBars(k string) []domain.Bar {
	out := make([]domain.Bar, len(r.bars[k]))
	copy(out, r.bars[k])
	sort.Slice(out, func(i, j int) bool { return out[i].OpenTime < out[j].OpenTime })
	return out
}

func (r *fakeRepo) GetBars(_ context.Context, sym domain.Symbol, interval string, limit int) ([]domain.Bar, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	all := r.sortedBars(ckey(sym, interval))
	if limit > 0 && len(all) > limit {
		all = all[len(all)-limit:]
	}
	return all, nil
}

func (r *fakeRepo) GetLatestBar(_ context.Context, sym domain.Symbol, interval string) (domain.Bar, error) {
	r.mu.Lock()
	defer r.mu.Unlock()
	all := r.sortedBars(ckey(sym, interval))
	if len(all) == 0 {
		return domain.Bar{}, data.ErrNotFound
	}
	return all[len(all)-1], nil
}

func makeBar(sym domain.Symbol, interval string, openMs int64, close string) domain.Bar {
	d := func(s string) decimal.Decimal { v, _ := decimal.NewFromString(s); return v }
	return domain.Bar{
		Symbol:    sym,
		Interval:  interval,
		OpenTime:  openMs,
		CloseTime: openMs + 59_999,
		Open:      d("100.0"),
		High:      d("110.0"),
		Low:       d("90.0"),
		Close:     d(close),
		Volume:    d("12.5"),
	}
}

// TestMarketData_CollectorWritesAndAPIServes is the headline integration test:
// feed fake bars into the collector, assert they land in the cache and repo,
// then verify the chi handlers return the expected envelope shape.
func TestMarketData_CollectorWritesAndAPIServes(t *testing.T) {
	cache := newFakeCache()
	repo := newFakeRepo()

	col := collector.New(cache, repo, collector.Options{
		BatchSize:     2,
		FlushInterval: 50 * time.Millisecond,
	})

	in := make(chan domain.Bar, 8)
	const sym = domain.Symbol("BTCUSDT")
	bars := []domain.Bar{
		makeBar(sym, "1m", 1_700_000_000_000, "101.0"),
		makeBar(sym, "1m", 1_700_000_060_000, "102.0"),
		makeBar(sym, "1m", 1_700_000_120_000, "103.0"),
	}
	for _, b := range bars {
		in <- b
	}
	close(in)

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	require.NoError(t, col.Run(ctx, in))

	// Cache: latest bar should be the third one.
	got, err := cache.GetLatestBar(ctx, sym, "1m")
	require.NoError(t, err)
	require.Equal(t, int64(1_700_000_120_000), got.OpenTime)
	require.Equal(t, "103", got.Close.String())

	// Repo: all three persisted.
	repoBars, err := repo.GetBars(ctx, sym, "1m", 10)
	require.NoError(t, err)
	require.Len(t, repoBars, 3)
	require.Equal(t, int64(1_700_000_000_000), repoBars[0].OpenTime)
	require.Equal(t, int64(1_700_000_120_000), repoBars[2].OpenTime)

	// Idempotency: re-inserting the same bars must not duplicate.
	require.NoError(t, repo.InsertBars(ctx, bars))
	again, _ := repo.GetBars(ctx, sym, "1m", 10)
	require.Len(t, again, 3)

	// HTTP layer: create a Fiber app with just the market routes.
	svc := market.NewService(cache, repo, []domain.Symbol{sym, "ETHUSDT"})
	app := newMarketApp(svc)

	do := func(path string) *http.Response {
		req := httptest.NewRequest(http.MethodGet, path, nil)
		resp, err := app.Test(req, -1)
		require.NoError(t, err)
		return resp
	}

	t.Run("symbols", func(t *testing.T) {
		resp := do("/api/market/symbols")
		require.Equal(t, http.StatusOK, resp.StatusCode)

		_, raw := decodeEnvelope(t, resp)
		require.JSONEq(t, `null`, string(raw["error"]))

		var data struct {
			Symbols []string `json:"symbols"`
		}
		require.NoError(t, json.Unmarshal(raw["data"], &data))
		require.Equal(t, []string{"BTCUSDT", "ETHUSDT"}, data.Symbols)
	})

	t.Run("candles", func(t *testing.T) {
		resp := do("/api/market/candles?symbol=BTCUSDT&interval=1m&limit=10")
		require.Equal(t, http.StatusOK, resp.StatusCode)

		_, raw := decodeEnvelope(t, resp)
		require.JSONEq(t, `null`, string(raw["error"]))

		var data struct {
			Symbol   string `json:"symbol"`
			Interval string `json:"interval"`
			Bars     []struct {
				Symbol   string `json:"symbol"`
				Interval string `json:"interval"`
				OpenTime int64  `json:"open_time"`
				Close    string `json:"close"`
			} `json:"bars"`
		}
		require.NoError(t, json.Unmarshal(raw["data"], &data))
		require.Equal(t, "BTCUSDT", data.Symbol)
		require.Equal(t, "1m", data.Interval)
		require.Len(t, data.Bars, 3)
		require.Equal(t, int64(1_700_000_000_000), data.Bars[0].OpenTime)
		require.Equal(t, "103", data.Bars[2].Close, "money fields must serialize as strings")
	})

	t.Run("snapshot cache hit", func(t *testing.T) {
		resp := do("/api/market/snapshot?symbol=BTCUSDT&interval=1m")
		require.Equal(t, http.StatusOK, resp.StatusCode)

		_, raw := decodeEnvelope(t, resp)
		require.JSONEq(t, `null`, string(raw["error"]))

		var data struct {
			Symbol   string `json:"symbol"`
			Interval string `json:"interval"`
			Source   string `json:"source"`
			Latest   struct {
				OpenTime int64  `json:"open_time"`
				Close    string `json:"close"`
			} `json:"latest"`
		}
		require.NoError(t, json.Unmarshal(raw["data"], &data))
		require.Equal(t, "cache", data.Source)
		require.Equal(t, int64(1_700_000_120_000), data.Latest.OpenTime)
		require.Equal(t, "103", data.Latest.Close)
	})

	t.Run("snapshot postgres fallback", func(t *testing.T) {
		emptyCache := newFakeCache()
		fbSvc := market.NewService(emptyCache, repo, []domain.Symbol{sym})
		fbApp := newMarketApp(fbSvc)
		req := httptest.NewRequest(http.MethodGet, "/api/market/snapshot?symbol=BTCUSDT&interval=1m", nil)
		resp, err := fbApp.Test(req, -1)
		require.NoError(t, err)
		require.Equal(t, http.StatusOK, resp.StatusCode)

		_, raw := decodeEnvelope(t, resp)
		var data struct {
			Source string `json:"source"`
			Latest struct {
				OpenTime int64 `json:"open_time"`
			} `json:"latest"`
		}
		require.NoError(t, json.Unmarshal(raw["data"], &data))
		require.Equal(t, "repo", data.Source)
		require.Equal(t, int64(1_700_000_120_000), data.Latest.OpenTime)
	})

	t.Run("snapshot not found", func(t *testing.T) {
		resp := do("/api/market/snapshot?symbol=ETHUSDT&interval=1m")
		require.Equal(t, http.StatusNotFound, resp.StatusCode)

		env, raw := decodeEnvelope(t, resp)
		require.JSONEq(t, `null`, string(raw["data"]))
		require.NotNil(t, env.Error)
		require.Equal(t, "not_found", env.Error.Code)
	})

	t.Run("candles validation", func(t *testing.T) {
		resp := do("/api/market/candles?interval=1m")
		require.Equal(t, http.StatusBadRequest, resp.StatusCode)

		env, _ := decodeEnvelope(t, resp)
		require.NotNil(t, env.Error)
		require.Equal(t, "validation_failed", env.Error.Code)
	})
}

// Sanity check: the data.ErrNotFound sentinel is exported and comparable.
func TestMarketData_ErrNotFoundIsExported(t *testing.T) {
	require.True(t, errors.Is(data.ErrNotFound, data.ErrNotFound))
}

// newMarketApp creates a minimal Fiber app with only market routes wired,
// used by HTTP-layer subtests to avoid spinning up the full server.
func newMarketApp(svc *market.Service) *fiber.App {
	app := fiber.New()
	handlers.RegisterRoutes(app, handlers.Deps{
		MarketSvc:  svc,
		BinanceCfg: binance.Config{},
		AIBaseURL:  "",
	})
	return app
}
