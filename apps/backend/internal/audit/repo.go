package audit

import (
	"context"
	"sort"
	"sync"
	"time"

	"github.com/jackc/pgx/v5/pgxpool"
)

// Repo persists audit entries.
type Repo interface {
	Insert(ctx context.Context, e Entry) error
	List(ctx context.Context, limit int) ([]Entry, error)
}

// MemoryRepo is the in-memory Repo for tests and dev.
type MemoryRepo struct {
	mu sync.RWMutex
	m  []Entry
}

func NewMemoryRepo() *MemoryRepo { return &MemoryRepo{} }

func (r *MemoryRepo) Insert(_ context.Context, e Entry) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	if e.CreatedAt.IsZero() {
		e.CreatedAt = time.Now().UTC()
	}
	r.m = append(r.m, e)
	return nil
}

func (r *MemoryRepo) List(_ context.Context, limit int) ([]Entry, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	out := make([]Entry, len(r.m))
	copy(out, r.m)
	sort.Slice(out, func(i, j int) bool { return out[i].CreatedAt.After(out[j].CreatedAt) })
	if limit > 0 && len(out) > limit {
		out = out[:limit]
	}
	return out, nil
}

// Count returns the row count (test helper).
func (r *MemoryRepo) Count() int {
	r.mu.RLock()
	defer r.mu.RUnlock()
	return len(r.m)
}

// Filter returns rows matching the given action (test helper).
func (r *MemoryRepo) Filter(action Action) []Entry {
	r.mu.RLock()
	defer r.mu.RUnlock()
	var out []Entry
	for _, e := range r.m {
		if e.Action == action {
			out = append(out, e)
		}
	}
	return out
}

// PostgresRepo persists audit entries in Postgres (table: audit_log).
type PostgresRepo struct {
	pool *pgxpool.Pool
}

func NewPostgresRepo(pool *pgxpool.Pool) *PostgresRepo { return &PostgresRepo{pool: pool} }

func (r *PostgresRepo) Insert(ctx context.Context, e Entry) error {
	const q = `INSERT INTO audit_log (id, action, actor, mode, entity, details, created_at)
		VALUES ($1,$2,$3,$4,$5,$6,$7)`
	_, err := r.pool.Exec(ctx, q,
		e.ID, string(e.Action), e.Actor, e.Mode, e.Entity, e.Details, e.CreatedAt)
	return err
}

func (r *PostgresRepo) List(ctx context.Context, limit int) ([]Entry, error) {
	if limit <= 0 {
		limit = 200
	}
	const q = `SELECT id, action, actor, mode, entity, details, created_at
		FROM audit_log ORDER BY created_at DESC LIMIT $1`
	rows, err := r.pool.Query(ctx, q, limit)
	if err != nil {
		return nil, err
	}
	defer rows.Close()
	var out []Entry
	for rows.Next() {
		var e Entry
		var act string
		if err := rows.Scan(&e.ID, &act, &e.Actor, &e.Mode, &e.Entity, &e.Details, &e.CreatedAt); err != nil {
			return nil, err
		}
		e.Action = Action(act)
		out = append(out, e)
	}
	return out, rows.Err()
}
