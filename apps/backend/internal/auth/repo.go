package auth

import (
	"context"
	"errors"
	"strings"
	"sync"
	"time"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
)

// Repo persists users.
type Repo interface {
	Create(ctx context.Context, u User) error
	GetByUsername(ctx context.Context, username string) (User, error)
	GetByID(ctx context.Context, id string) (User, error)
}

// MemoryRepo is an in-memory Repo for tests and dev.
type MemoryRepo struct {
	mu    sync.RWMutex
	byID  map[string]User
	byUsr map[string]string
}

func NewMemoryRepo() *MemoryRepo {
	return &MemoryRepo{byID: map[string]User{}, byUsr: map[string]string{}}
}

func (r *MemoryRepo) Create(_ context.Context, u User) error {
	r.mu.Lock()
	defer r.mu.Unlock()
	key := strings.ToLower(u.Username)
	if _, ok := r.byUsr[key]; ok {
		return ErrUserExists
	}
	now := time.Now().UTC()
	if u.CreatedAt.IsZero() {
		u.CreatedAt = now
	}
	u.UpdatedAt = now
	r.byID[u.ID] = u
	r.byUsr[key] = u.ID
	return nil
}

func (r *MemoryRepo) GetByUsername(_ context.Context, username string) (User, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	id, ok := r.byUsr[strings.ToLower(username)]
	if !ok {
		return User{}, ErrUserNotFound
	}
	return r.byID[id], nil
}

func (r *MemoryRepo) GetByID(_ context.Context, id string) (User, error) {
	r.mu.RLock()
	defer r.mu.RUnlock()
	u, ok := r.byID[id]
	if !ok {
		return User{}, ErrUserNotFound
	}
	return u, nil
}

// PostgresRepo persists users in Postgres.
type PostgresRepo struct {
	pool *pgxpool.Pool
}

func NewPostgresRepo(pool *pgxpool.Pool) *PostgresRepo {
	return &PostgresRepo{pool: pool}
}

func (r *PostgresRepo) Create(ctx context.Context, u User) error {
	const q = `INSERT INTO users (id, username, password_hash, role) VALUES ($1, $2, $3, $4)`
	_, err := r.pool.Exec(ctx, q, u.ID, strings.ToLower(u.Username), u.PasswordHash, string(u.Role))
	if err != nil {
		// 23505 = unique_violation
		if strings.Contains(err.Error(), "23505") {
			return ErrUserExists
		}
		return err
	}
	return nil
}

func (r *PostgresRepo) GetByUsername(ctx context.Context, username string) (User, error) {
	const q = `SELECT id, username, password_hash, role, created_at, updated_at FROM users WHERE username = $1`
	row := r.pool.QueryRow(ctx, q, strings.ToLower(username))
	return scanUser(row)
}

func (r *PostgresRepo) GetByID(ctx context.Context, id string) (User, error) {
	const q = `SELECT id, username, password_hash, role, created_at, updated_at FROM users WHERE id = $1`
	row := r.pool.QueryRow(ctx, q, id)
	return scanUser(row)
}

func scanUser(row pgx.Row) (User, error) {
	var u User
	var role string
	if err := row.Scan(&u.ID, &u.Username, &u.PasswordHash, &role, &u.CreatedAt, &u.UpdatedAt); err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return User{}, ErrUserNotFound
		}
		return User{}, err
	}
	u.Role = Role(role)
	return u, nil
}
