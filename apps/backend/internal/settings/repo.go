package settings

import (
	"context"
	"errors"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"
)

// Repo persists per-user settings.
type Repo interface {
	Get(ctx context.Context, userID string) (Settings, error)
	Upsert(ctx context.Context, s Settings) error
}

// MemoryRepo is an in-memory Repo for tests and dev.
type MemoryRepo struct {
	mu sync.RWMutex
	m  map[string]Settings
}

func NewMemoryRepo() *MemoryRepo { return &MemoryRepo{m: map[string]Settings{}} }

func (r *MemoryRepo) Get(_ context.Context, userID string) (Settings, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	s, ok := r.m[userID]
	if !ok {
		return Settings{}, ErrNotFound
	}
	return s, nil
}

func (r *MemoryRepo) Upsert(_ context.Context, s Settings) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	s.UpdatedAt = time.Now().UTC()
	r.m[s.UserID] = s
	return nil
}

// PostgresRepo persists settings in Postgres (table: user_settings).
type PostgresRepo struct {
	pool *pgxpool.Pool
}

func NewPostgresRepo(pool *pgxpool.Pool) *PostgresRepo { return &PostgresRepo{pool: pool} }

func (r *PostgresRepo) Get(ctx context.Context, userID string) (Settings, error) {
	const q = `SELECT user_id, default_symbol, default_timeframe,
		max_position_pct, max_daily_drawdown_pct, max_slippage_bps,
		notify_email, notify_webhook_url, updated_at
		FROM user_settings WHERE user_id = $1`
	row := r.pool.QueryRow(ctx, q, userID)
	var s Settings
	var posPct, ddPct decimal.Decimal
	if err := row.Scan(&s.UserID, &s.DefaultSymbol, &s.DefaultTimeframe,
		&posPct, &ddPct, &s.MaxSlippageBps,
		&s.NotifyEmail, &s.NotifyWebhookURL, &s.UpdatedAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return Settings{}, ErrNotFound
		}
		return Settings{}, err
	}
	s.MaxPositionPct = posPct
	s.MaxDailyDrawdownPct = ddPct
	return s, nil
}

func (r *PostgresRepo) Upsert(ctx context.Context, s Settings) error {
	const q = `INSERT INTO user_settings
		(user_id, default_symbol, default_timeframe,
		 max_position_pct, max_daily_drawdown_pct, max_slippage_bps,
		 notify_email, notify_webhook_url, updated_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7,$8, now())
		ON CONFLICT (user_id) DO UPDATE SET
			default_symbol = EXCLUDED.default_symbol,
			default_timeframe = EXCLUDED.default_timeframe,
			max_position_pct = EXCLUDED.max_position_pct,
			max_daily_drawdown_pct = EXCLUDED.max_daily_drawdown_pct,
			max_slippage_bps = EXCLUDED.max_slippage_bps,
			notify_email = EXCLUDED.notify_email,
			notify_webhook_url = EXCLUDED.notify_webhook_url,
			updated_at = now()`
	_, err := r.pool.Exec(ctx, q, s.UserID, s.DefaultSymbol, s.DefaultTimeframe,
		s.MaxPositionPct, s.MaxDailyDrawdownPct, s.MaxSlippageBps,
		s.NotifyEmail, s.NotifyWebhookURL)
	return err
}
