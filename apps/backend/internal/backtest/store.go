package backtest

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"sort"
	"sync"

	"github.com/jackc/pgx/v5"
	"github.com/jackc/pgx/v5/pgxpool"
	"github.com/shopspring/decimal"
)

func mustDec(s string) decimal.Decimal {
	if s == "" {
		return decimal.Zero
	}
	d, err := decimal.NewFromString(s)
	if err != nil {
		return decimal.Zero
	}
	return d
}

// ErrNotFound is returned by Store.Get when no row matches the id.
var ErrNotFound = errors.New("backtest: not found")

// Store persists backtest results.
type Store interface {
	Insert(ctx context.Context, r Result) error
	Get(ctx context.Context, id string) (Result, error)
	List(ctx context.Context, limit, offset int) ([]Result, int, error)
}

// MemoryStore is the default in-process Store. Used by tests and as a fallback
// when Postgres isn't wired up at startup.
type MemoryStore struct {
	mu      sync.RWMutex
	results []Result
}

func NewMemoryStore() *MemoryStore { return &MemoryStore{} }

func (s *MemoryStore) Insert(_ context.Context, r Result) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.results = append(s.results, r)
	return nil
}

func (s *MemoryStore) Get(_ context.Context, id string) (Result, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	for _, r := range s.results {
		if r.ID == id {
			return r, nil
		}
	}
	return Result{}, ErrNotFound
}

func (s *MemoryStore) List(_ context.Context, limit, offset int) ([]Result, int, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	out := make([]Result, len(s.results))
	copy(out, s.results)
	sort.Slice(out, func(i, j int) bool { return out[i].CreatedMs > out[j].CreatedMs })
	total := len(out)

	if offset > 0 {
		if offset >= len(out) {
			return []Result{}, total, nil
		}
		out = out[offset:]
	}
	if limit > 0 && len(out) > limit {
		out = out[:limit]
	}
	return out, total, nil
}

// PostgresStore implements Store against pgxpool. It serializes the equity
// curve and trade list as JSONB; metrics live in dedicated columns for query.
type PostgresStore struct{ pool *pgxpool.Pool }

func NewPostgresStore(pool *pgxpool.Pool) *PostgresStore { return &PostgresStore{pool: pool} }

const insertResultSQL = `
INSERT INTO backtest_results (
    id, symbol, interval, strategy_name, config_json,
    start_ms, end_ms, bars_processed,
    initial_equity, final_equity,
    total_trades, winning_trades, losing_trades,
    win_rate, profit_factor, total_return, max_drawdown, sharpe_ratio,
    equity_curve_json, trades_json, created_ms
) VALUES (
    $1,$2,$3,$4,$5,
    $6,$7,$8,
    $9,$10,
    $11,$12,$13,
    $14,$15,$16,$17,$18,
    $19,$20,$21
)
`

func (s *PostgresStore) Insert(ctx context.Context, r Result) error {
	cfg, err := json.Marshal(r.Config)
	if err != nil {
		return fmt.Errorf("backtest store: marshal config: %w", err)
	}
	curve, err := json.Marshal(r.EquityCurve)
	if err != nil {
		return fmt.Errorf("backtest store: marshal curve: %w", err)
	}
	trades, err := json.Marshal(r.Trades)
	if err != nil {
		return fmt.Errorf("backtest store: marshal trades: %w", err)
	}

	_, err = s.pool.Exec(ctx, insertResultSQL,
		r.ID, string(r.Config.Symbol), r.Config.Interval, r.Config.StrategyName, string(cfg),
		r.StartMs, r.EndMs, r.BarsProcessed,
		r.InitialEquity.String(), r.FinalEquity.String(),
		r.Metrics.TotalTrades, r.Metrics.WinningTrades, r.Metrics.LosingTrades,
		r.Metrics.WinRate.String(), r.Metrics.ProfitFactor.String(),
		r.Metrics.TotalReturn.String(), r.Metrics.MaxDrawdown.String(), r.Metrics.SharpeRatio.String(),
		string(curve), string(trades), r.CreatedMs,
	)
	if err != nil {
		return fmt.Errorf("backtest store: insert: %w", err)
	}
	return nil
}

const selectResultSQL = `
SELECT id, config_json, start_ms, end_ms, bars_processed,
       initial_equity, final_equity,
       total_trades, winning_trades, losing_trades,
       win_rate, profit_factor, total_return, max_drawdown, sharpe_ratio,
       equity_curve_json, trades_json, created_ms
FROM backtest_results
`

func (s *PostgresStore) Get(ctx context.Context, id string) (Result, error) {
	row := s.pool.QueryRow(ctx, selectResultSQL+" WHERE id = $1", id)
	r, err := scanResult(row)
	if err != nil {
		if errors.Is(err, pgx.ErrNoRows) {
			return Result{}, ErrNotFound
		}
		return Result{}, fmt.Errorf("backtest store: get: %w", err)
	}
	return r, nil
}

func (s *PostgresStore) List(ctx context.Context, limit, offset int) ([]Result, int, error) {
	if limit <= 0 {
		limit = 100
	}
	var total int
	if err := s.pool.QueryRow(ctx, "SELECT COUNT(*) FROM backtest_results").Scan(&total); err != nil {
		return nil, 0, fmt.Errorf("backtest store: count: %w", err)
	}
	rows, err := s.pool.Query(ctx,
		selectResultSQL+" ORDER BY created_ms DESC LIMIT $1 OFFSET $2",
		limit, offset)
	if err != nil {
		return nil, 0, fmt.Errorf("backtest store: list: %w", err)
	}
	defer rows.Close()

	out := make([]Result, 0, limit)
	for rows.Next() {
		r, err := scanResult(rows)
		if err != nil {
			return nil, 0, err
		}
		out = append(out, r)
	}
	return out, total, rows.Err()
}

type scannable interface {
	Scan(dest ...any) error
}

func scanResult(s scannable) (Result, error) {
	var (
		r                                                         Result
		cfgJSON, curveJSON, tradesJSON                            string
		initialS, finalS                                          string
		winRateS, profitS, retS, ddS, sharpeS                     string
	)
	if err := s.Scan(
		&r.ID, &cfgJSON, &r.StartMs, &r.EndMs, &r.BarsProcessed,
		&initialS, &finalS,
		&r.Metrics.TotalTrades, &r.Metrics.WinningTrades, &r.Metrics.LosingTrades,
		&winRateS, &profitS, &retS, &ddS, &sharpeS,
		&curveJSON, &tradesJSON, &r.CreatedMs,
	); err != nil {
		return Result{}, err
	}
	if err := json.Unmarshal([]byte(cfgJSON), &r.Config); err != nil {
		return Result{}, fmt.Errorf("backtest store: unmarshal config: %w", err)
	}
	if err := json.Unmarshal([]byte(curveJSON), &r.EquityCurve); err != nil {
		return Result{}, fmt.Errorf("backtest store: unmarshal curve: %w", err)
	}
	if err := json.Unmarshal([]byte(tradesJSON), &r.Trades); err != nil {
		return Result{}, fmt.Errorf("backtest store: unmarshal trades: %w", err)
	}
	r.InitialEquity = mustDec(initialS)
	r.FinalEquity = mustDec(finalS)
	r.Metrics.WinRate = mustDec(winRateS)
	r.Metrics.ProfitFactor = mustDec(profitS)
	r.Metrics.TotalReturn = mustDec(retS)
	r.Metrics.MaxDrawdown = mustDec(ddS)
	r.Metrics.SharpeRatio = mustDec(sharpeS)
	return r, nil
}
