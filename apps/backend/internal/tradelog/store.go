package tradelog

import (
	"context"
	"sort"
	"sync"

	"github.com/shopspring/decimal"
)

// Store is the persistence boundary for trade records. Implementations must
// be safe for concurrent use.
type Store interface {
	Insert(ctx context.Context, r Record) error
	List(ctx context.Context, f Filter) ([]Record, int, error)
	Summary(ctx context.Context, period Period, nowMs int64) (Summary, error)
}

// MemoryStore is an in-memory Store implementation — used by tests and as the
// default until a Postgres-backed store is wired in at process startup.
type MemoryStore struct {
	mu      sync.RWMutex
	records []Record
}

func NewMemoryStore() *MemoryStore { return &MemoryStore{} }

func (s *MemoryStore) Insert(_ context.Context, r Record) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.records = append(s.records, r)
	return nil
}

func (s *MemoryStore) List(_ context.Context, f Filter) ([]Record, int, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	out := make([]Record, 0, len(s.records))
	for _, r := range s.records {
		if !match(r, f) {
			continue
		}
		out = append(out, r)
	}
	sort.Slice(out, func(i, j int) bool { return out[i].TimestampMs > out[j].TimestampMs })
	total := len(out)

	if f.Offset > 0 {
		if f.Offset >= len(out) {
			return []Record{}, total, nil
		}
		out = out[f.Offset:]
	}
	if f.Limit > 0 && len(out) > f.Limit {
		out = out[:f.Limit]
	}
	return out, total, nil
}

func (s *MemoryStore) Summary(_ context.Context, period Period, nowMs int64) (Summary, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()

	from, to := windowFor(period, nowMs)
	sum := Summary{Period: period, FromMs: from, ToMs: to}

	for _, r := range s.records {
		if period != PeriodAll {
			if r.TimestampMs < from || r.TimestampMs > to {
				continue
			}
		}
		sum.Count++
		switch r.Side {
		case "buy":
			sum.BuyCount++
		case "sell":
			sum.SellCount++
		}
		sum.GrossVolume = sum.GrossVolume.Add(r.Qty.Mul(r.FillPrice))
		sum.RealizedPL = sum.RealizedPL.Add(r.RealizedPL)
		sum.TotalFees = sum.TotalFees.Add(r.Fee)
		switch {
		case r.RealizedPL.GreaterThan(decimal.Zero):
			sum.WinningTrades++
		case r.RealizedPL.LessThan(decimal.Zero):
			sum.LosingTrades++
		}
	}
	return sum, nil
}

func match(r Record, f Filter) bool {
	if f.Mode != "" && r.Mode != f.Mode {
		return false
	}
	if f.Symbol != "" && r.Symbol != f.Symbol {
		return false
	}
	if f.Side != "" && r.Side != f.Side {
		return false
	}
	if f.Strategy != "" && r.Strategy != f.Strategy {
		return false
	}
	if f.FromMs > 0 && r.TimestampMs < f.FromMs {
		return false
	}
	if f.ToMs > 0 && r.TimestampMs > f.ToMs {
		return false
	}
	return true
}

const (
	msPerDay  int64 = 24 * 60 * 60 * 1000
	msPerWeek int64 = 7 * msPerDay
)

func windowFor(p Period, nowMs int64) (int64, int64) {
	switch p {
	case PeriodDay:
		return nowMs - msPerDay, nowMs
	case PeriodWeek:
		return nowMs - msPerWeek, nowMs
	default:
		return 0, nowMs
	}
}
