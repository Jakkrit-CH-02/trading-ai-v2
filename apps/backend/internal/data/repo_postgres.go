package data

import (
	"context"
	"errors"
	"fmt"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// PostgresRepo implements Repo against pgxpool.
//
// Bars are inserted with ON CONFLICT DO NOTHING so a re-broadcast of the
// same closed kline is idempotent (acceptance criterion: no duplicates by
// symbol/interval/open_time).
type PostgresRepo struct {
	pool *pgxpool.Pool
}

// NewPostgresRepo wraps a pool.
func NewPostgresRepo(pool *pgxpool.Pool) *PostgresRepo {
	return &PostgresRepo{pool: pool}
}

const insertBarSQL = `
INSERT INTO bar_history
    (symbol, interval, open_time, close_time, open, high, low, close, volume)
VALUES
    ($1,$2,$3,$4,$5,$6,$7,$8,$9)
ON CONFLICT (symbol, interval, open_time) DO NOTHING
`

// InsertBars writes a batch of bars in a single transaction.
func (r *PostgresRepo) InsertBars(ctx context.Context, bars []domain.Bar) error {
	if len(bars) == 0 {
		return nil
	}
	tx, err := r.pool.Begin(ctx)
	if err != nil {
		return fmt.Errorf("pg repo: begin: %w", err)
	}
	defer func() { _ = tx.Rollback(ctx) }()

	batch := &pgx.Batch{}
	for _, b := range bars {
		batch.Queue(insertBarSQL,
			string(b.Symbol), b.Interval, b.OpenTime, b.CloseTime,
			b.Open.String(), b.High.String(), b.Low.String(), b.Close.String(), b.Volume.String(),
		)
	}
	br := tx.SendBatch(ctx, batch)
	for range bars {
		if _, err := br.Exec(); err != nil {
			_ = br.Close()
			return fmt.Errorf("pg repo: insert bar: %w", err)
		}
	}
	if err := br.Close(); err != nil {
		return fmt.Errorf("pg repo: close batch: %w", err)
	}
	if err := tx.Commit(ctx); err != nil {
		return fmt.Errorf("pg repo: commit: %w", err)
	}
	return nil
}

const selectBarsSQL = `
SELECT symbol, interval, open_time, close_time, open, high, low, close, volume
FROM bar_history
WHERE symbol = $1 AND interval = $2
ORDER BY open_time DESC
LIMIT $3
`

// GetBars returns the most recent `limit` bars in ascending open_time order.
func (r *PostgresRepo) GetBars(ctx context.Context, sym domain.Symbol, interval string, limit int) ([]domain.Bar, error) {
	if limit <= 0 {
		limit = 100
	}
	rows, err := r.pool.Query(ctx, selectBarsSQL, string(sym), interval, limit)
	if err != nil {
		return nil, fmt.Errorf("pg repo: query: %w", err)
	}
	defer rows.Close()

	out := make([]domain.Bar, 0, limit)
	for rows.Next() {
		bar, err := scanBar(rows)
		if err != nil {
			return nil, err
		}
		out = append(out, bar)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("pg repo: scan: %w", err)
	}
	// Reverse to ascending.
	for i, j := 0, len(out)-1; i < j; i, j = i+1, j-1 {
		out[i], out[j] = out[j], out[i]
	}
	return out, nil
}

// GetLatestBar returns the single most recent bar.
func (r *PostgresRepo) GetLatestBar(ctx context.Context, sym domain.Symbol, interval string) (domain.Bar, error) {
	row := r.pool.QueryRow(ctx, selectBarsSQL, string(sym), interval, 1)
	bar, err := scanBar(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return domain.Bar{}, ErrNotFound
		}
		return domain.Bar{}, err
	}
	return bar, nil
}

// scannable is the small subset of pgx.Row / pgx.Rows we need.
type scannable interface {
	Scan(dest ...any) error
}

func scanBar(s scannable) (domain.Bar, error) {
	var (
		sym, interval                       string
		openTime, closeTime                 int64
		openS, highS, lowS, closeS, volumeS string
	)
	if err := s.Scan(&sym, &interval, &openTime, &closeTime, &openS, &highS, &lowS, &closeS, &volumeS); err != nil {
		return domain.Bar{}, err
	}
	open, err := decimal.NewFromString(openS)
	if err != nil {
		return domain.Bar{}, fmt.Errorf("pg repo: parse open: %w", err)
	}
	high, err := decimal.NewFromString(highS)
	if err != nil {
		return domain.Bar{}, fmt.Errorf("pg repo: parse high: %w", err)
	}
	low, err := decimal.NewFromString(lowS)
	if err != nil {
		return domain.Bar{}, fmt.Errorf("pg repo: parse low: %w", err)
	}
	cls, err := decimal.NewFromString(closeS)
	if err != nil {
		return domain.Bar{}, fmt.Errorf("pg repo: parse close: %w", err)
	}
	vol, err := decimal.NewFromString(volumeS)
	if err != nil {
		return domain.Bar{}, fmt.Errorf("pg repo: parse volume: %w", err)
	}
	return domain.Bar{
		Symbol:    domain.Symbol(sym),
		Interval:  interval,
		OpenTime:  openTime,
		CloseTime: closeTime,
		Open:      open,
		High:      high,
		Low:       low,
		Close:     cls,
		Volume:    vol,
	}, nil
}
