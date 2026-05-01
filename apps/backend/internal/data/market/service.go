// Package market exposes the read-side of market data: cache-first snapshot
// and candle history queries served via chi handlers.
package market

import (
	"context"
	"errors"
	"fmt"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/data"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// Service answers /api/market/* queries.
type Service struct {
	cache   data.Cache
	repo    data.Repo
	symbols []domain.Symbol
}

// NewService wires cache, repo and the configured symbol list.
func NewService(cache data.Cache, repo data.Repo, symbols []domain.Symbol) *Service {
	return &Service{cache: cache, repo: repo, symbols: symbols}
}

// Symbols returns the configured tradable symbols (deep copy).
func (s *Service) Symbols() []domain.Symbol {
	out := make([]domain.Symbol, len(s.symbols))
	copy(out, s.symbols)
	return out
}

// Candles returns history for symbol/interval, ascending open_time.
func (s *Service) Candles(ctx context.Context, sym domain.Symbol, interval string, limit int) ([]domain.Bar, error) {
	if sym == "" || interval == "" {
		return nil, fmt.Errorf("market: symbol and interval required")
	}
	if s.repo == nil {
		return nil, fmt.Errorf("market: repo not configured")
	}
	return s.repo.GetBars(ctx, sym, interval, limit)
}

// Snapshot returns the latest bar — cache hit, postgres fallback.
func (s *Service) Snapshot(ctx context.Context, sym domain.Symbol, interval string) (domain.Bar, error) {
	if sym == "" || interval == "" {
		return domain.Bar{}, fmt.Errorf("market: symbol and interval required")
	}
	if s.cache != nil {
		bar, err := s.cache.GetLatestBar(ctx, sym, interval)
		if err == nil {
			return bar, nil
		}
		if !errors.Is(err, data.ErrNotFound) {
			// Cache failure should not block the read; fall through to repo.
			_ = err
		}
	}
	if s.repo == nil {
		return domain.Bar{}, data.ErrNotFound
	}
	return s.repo.GetLatestBar(ctx, sym, interval)
}
