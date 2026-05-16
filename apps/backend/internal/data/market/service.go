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
	hub     *Hub
}

// NewService wires cache, repo, the configured symbol list, and the bar hub.
func NewService(cache data.Cache, repo data.Repo, symbols []domain.Symbol, hub *Hub) *Service {
	return &Service{cache: cache, repo: repo, symbols: symbols, hub: hub}
}

// Hub returns the bar pub/sub hub for WebSocket fan-out.
func (s *Service) Hub() *Hub { return s.hub }

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
// The second return value is "cache" or "repo" indicating the data source.
func (s *Service) Snapshot(ctx context.Context, sym domain.Symbol, interval string) (domain.Bar, string, error) {
	if sym == "" || interval == "" {
		return domain.Bar{}, "", fmt.Errorf("market: symbol and interval required")
	}
	if s.cache != nil {
		bar, err := s.cache.GetLatestBar(ctx, sym, interval)
		if err == nil {
			return bar, "cache", nil
		}
		if !errors.Is(err, data.ErrNotFound) {
			// Cache failure should not block the read; fall through to repo.
			_ = err
		}
	}
	if s.repo == nil {
		return domain.Bar{}, "", data.ErrNotFound
	}
	bar, err := s.repo.GetLatestBar(ctx, sym, interval)
	if err != nil {
		return domain.Bar{}, "", err
	}
	return bar, "repo", nil
}
