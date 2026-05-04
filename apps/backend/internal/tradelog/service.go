package tradelog

import (
	"context"
	"fmt"
	"log/slog"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/paper"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
)

// Service is the application-facing facade for recording and querying trades.
type Service struct {
	store Store
}

func NewService(store Store) *Service { return &Service{store: store} }

// Record persists a Record. If r.ID is empty, a ULID is generated.
func (s *Service) Record(ctx context.Context, r Record) (Record, error) {
	if r.ID == "" {
		r.ID = ids.New()
	}
	if r.TimestampMs <= 0 {
		return Record{}, fmt.Errorf("tradelog: timestamp_ms required")
	}
	if r.Symbol == "" {
		return Record{}, fmt.Errorf("tradelog: symbol required")
	}
	if r.Mode == "" {
		return Record{}, fmt.Errorf("tradelog: mode required")
	}
	if err := s.store.Insert(ctx, r); err != nil {
		return Record{}, fmt.Errorf("tradelog: insert: %w", err)
	}
	slog.InfoContext(ctx, "trade recorded",
		"service", "tradelog",
		"mode", string(r.Mode),
		"symbol", string(r.Symbol),
		"order_id", r.OrderID,
		"signal_id", r.SignalID,
		"side", string(r.Side),
		"qty", r.Qty.String(),
		"fill_price", r.FillPrice.String(),
		"realized_pl", r.RealizedPL.String(),
	)
	return r, nil
}

// List returns matching records (newest first) plus total count for pagination.
func (s *Service) List(ctx context.Context, f Filter) ([]Record, int, error) {
	return s.store.List(ctx, f)
}

// Summary aggregates the given Period.
func (s *Service) Summary(ctx context.Context, p Period, nowMs int64) (Summary, error) {
	return s.store.Summary(ctx, p, nowMs)
}

// SubscribePaper consumes paper.TradeLogEvent values from ch and persists each
// one as a Record tagged with ModePaper. It returns when ctx is canceled or ch
// is closed. Intended to be run in its own goroutine.
func (s *Service) SubscribePaper(ctx context.Context, ch <-chan paper.TradeLogEvent) {
	for {
		select {
		case <-ctx.Done():
			return
		case evt, ok := <-ch:
			if !ok {
				return
			}
			r := Record{
				Mode:        domain.ModePaper,
				Symbol:      evt.Symbol,
				Side:        evt.Side,
				OrderID:     evt.OrderID,
				Qty:         evt.Qty,
				FillPrice:   evt.FillPrice,
				Fee:         decimal.Zero,
				RealizedPL:  evt.RealizedPL,
				CashAfter:   evt.Cash,
				TimestampMs: evt.TimestampMs,
			}
			if _, err := s.Record(ctx, r); err != nil {
				slog.ErrorContext(ctx, "tradelog: record paper event",
					"service", "tradelog",
					"order_id", evt.OrderID,
					"err", err.Error(),
				)
			}
		}
	}
}
