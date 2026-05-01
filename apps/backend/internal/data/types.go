// Package data owns persistence and retrieval of market candles.
//
// It defines two narrow interfaces that decouple the collector and the
// market read API from concrete Redis / Postgres clients:
//
//	Cache — fast latest-bar lookup, written on every tick.
//	Repo  — durable history, written in batches as bars close.
//
// The collector subpackage drives writes; the market subpackage reads.
package data

import (
	"context"
	"errors"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// ErrNotFound is returned by Cache and Repo when no bar matches the query.
var ErrNotFound = errors.New("data: not found")

// Cache stores the most recent bar per (symbol, interval). All implementations
// must be safe for concurrent use.
type Cache interface {
	SetLatestBar(ctx context.Context, bar domain.Bar) error
	GetLatestBar(ctx context.Context, symbol domain.Symbol, interval string) (domain.Bar, error)
}

// Repo persists closed bars and serves history queries.
type Repo interface {
	InsertBars(ctx context.Context, bars []domain.Bar) error
	GetBars(ctx context.Context, symbol domain.Symbol, interval string, limit int) ([]domain.Bar, error)
	GetLatestBar(ctx context.Context, symbol domain.Symbol, interval string) (domain.Bar, error)
}
