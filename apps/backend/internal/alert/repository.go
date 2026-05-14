package alert

import (
	"context"
	"errors"
	"sort"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Repo persists alerts.
type Repo interface {
	Insert(ctx context.Context, a Alert) error
	List(ctx context.Context, limit int) ([]Alert, error)
	Ack(ctx context.Context, id string) error
}

// MemoryRepo is an in-memory Repo for tests and dev.
type MemoryRepo struct {
	mu sync.RWMutex
	m  map[string]Alert
}

func NewMemoryRepo() *MemoryRepo { return &MemoryRepo{m: map[string]Alert{}} }

func (r *MemoryRepo) Insert(_ context.Context, a Alert) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if a.CreatedAt.IsZero() {
		a.CreatedAt = time.Now().UTC()
	}
	r.m[a.ID] = a
	return nil
}

func (r *MemoryRepo) List(_ context.Context, limit int) ([]Alert, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]Alert, 0, len(r.m))
	for _, a := range r.m {
		out = append(out, a)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].CreatedAt.After(out[j].CreatedAt)
	})
	if limit > 0 && len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

func (r *MemoryRepo) Ack(_ context.Context, id string) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	a, ok := r.m[id]
	if !ok {
		return ErrNotFound
	}
	a.Read = true
	r.m[id] = a
	return nil
}

// Count returns the number of stored alerts (test helper).
func (r *MemoryRepo) Count() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.m)
}

// PostgresRepo persists alerts in Postgres (table: alerts).
type PostgresRepo struct {
	pool *pgxpool.Pool
}

func NewPostgresRepo(pool *pgxpool.Pool) *PostgresRepo { return &PostgresRepo{pool: pool} }

func (r *PostgresRepo) Insert(ctx context.Context, a Alert) error {
	const q = `INSERT INTO alerts (id, type, severity, message, entity, read, created_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7)`
	_, err := r.pool.Exec(ctx, q,
		a.ID, string(a.Type), string(a.Severity), a.Message, a.Entity, a.Read, a.CreatedAt)
	return err
}

func (r *PostgresRepo) List(ctx context.Context, limit int) ([]Alert, error) {
	if limit <= 0 {
		limit = 200
	}
	const q = `SELECT id, type, severity, message, entity, read, created_at
		FROM alerts ORDER BY created_at DESC LIMIT $1`
	rows, err := r.pool.Query(ctx, q, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Alert
	for rows.Next() {
		var a Alert
		var typ, sev string
		if err := rows.Scan(&a.ID, &typ, &sev, &a.Message, &a.Entity, &a.Read, &a.CreatedAt); err != nil {
			return nil, err
		}
		a.Type = Type(typ)
		a.Severity = Severity(sev)
		out = append(out, a)
	}
	return out, rows.Err()
}

func (r *PostgresRepo) Ack(ctx context.Context, id string) error {
	const q = `UPDATE alerts SET read = TRUE WHERE id = $1`
	tag, err := r.pool.Exec(ctx, q, id)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return ErrNotFound
		}
		return err
	}
	if tag.RowsAffected() == 0 {
		return ErrNotFound
	}
	return nil
}
