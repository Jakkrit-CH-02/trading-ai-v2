package backtest

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

type fakeBarsRepo struct {
	bars      []domain.Bar
	inserted  []domain.Bar
	getCalled int
}

func (r *fakeBarsRepo) InsertBars(_ context.Context, bars []domain.Bar) error {
	r.inserted = append(r.inserted, bars...)
	return nil
}

func (r *fakeBarsRepo) GetBars(_ context.Context, _ domain.Symbol, _ string, _ int) ([]domain.Bar, error) {
	r.getCalled++
	return r.bars, nil
}

func (r *fakeBarsRepo) GetLatestBar(_ context.Context, _ domain.Symbol, _ string) (domain.Bar, error) {
	return domain.Bar{}, nil
}

type fakeKlineFetcher struct {
	lastQuery binance.KlinesQuery
	bars      []domain.Bar
}

func (f *fakeKlineFetcher) GetKlines(_ context.Context, q binance.KlinesQuery) ([]domain.Bar, error) {
	f.lastQuery = q
	return f.bars, nil
}

func TestBuildKlinesQuery_ExpandsEqualRangeByLimit(t *testing.T) {
	cfg := Config{
		Symbol:   "BTCUSDT",
		Interval: "1m",
		FromMs:   1_700_000_000_000,
		ToMs:     1_700_000_000_000,
	}

	q := buildKlinesQuery(cfg, 5)
	require.Equal(t, int64(1_699_999_760_000), q.StartMs)
	require.Equal(t, cfg.ToMs, q.EndMs)
}

func TestLoadBars_FallsBackToRemoteAndPersists(t *testing.T) {
	repo := &fakeBarsRepo{}
	remoteBars := []domain.Bar{
		{
			Symbol:    "BTCUSDT",
			Interval:  "1m",
			OpenTime:  1,
			CloseTime: 2,
			Open:      decimal.NewFromInt(100),
			High:      decimal.NewFromInt(101),
			Low:       decimal.NewFromInt(99),
			Close:     decimal.NewFromInt(100),
			Volume:    decimal.NewFromInt(1),
		},
	}
	fetcher := &fakeKlineFetcher{bars: remoteBars}
	h := NewHandler(nil, repo, nil, nil).WithRemoteFetcher(fetcher)

	bars, err := h.loadBars(context.Background(), Config{
		Symbol:   "BTCUSDT",
		Interval: "1m",
		FromMs:   1000,
		ToMs:     2000,
	}, 100)
	require.NoError(t, err)
	require.Len(t, bars, 1)
	require.Equal(t, remoteBars, bars)
	require.Len(t, repo.inserted, 1)
	require.Equal(t, "BTCUSDT", fetcher.lastQuery.Symbol)
	require.Equal(t, "1m", fetcher.lastQuery.Interval)
}
