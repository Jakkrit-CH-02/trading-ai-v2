package order

import (
	"context"
	"fmt"
	"log/slog"
	"sync"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
)

// Manager turns a ValidatedSignal into an Order, dispatches it via the Router
// to the mode-specific Executor, and records idempotency so the same signal
// cannot place two orders.
type Manager struct {
	router *Router
	mode   domain.Mode

	mu   sync.Mutex
	seen map[string]domain.Order // idempotency key -> placed order
}

func NewManager(router *Router, mode domain.Mode) *Manager {
	return &Manager{
		router: router,
		mode:   mode,
		seen:   make(map[string]domain.Order),
	}
}

// Submit builds an order from a ValidatedSignal and routes it for execution.
// The signal's ID is the idempotency key — re-submitting the same signal
// returns the previously placed order without contacting the executor again.
func (m *Manager) Submit(ctx context.Context, vs risk.ValidatedSignal) (domain.Order, error) {
	key := vs.Signal.ID
	if key == "" {
		return domain.Order{}, fmt.Errorf("order: signal id required for idempotency")
	}

	m.mu.Lock()
	if existing, ok := m.seen[key]; ok {
		m.mu.Unlock()
		slog.InfoContext(ctx, "order idempotent replay",
			"service", "order",
			"mode", string(m.mode),
			"symbol", string(existing.Symbol),
			"order_id", existing.ID,
			"signal_id", key,
		)
		return existing, nil
	}
	m.mu.Unlock()

	exec, err := m.router.Route(m.mode)
	if err != nil {
		return domain.Order{}, fmt.Errorf("order: route: %w", err)
	}

	o := buildOrder(vs, m.mode)

	placed, err := exec.Place(ctx, o)
	if err != nil {
		slog.WarnContext(ctx, "order rejected",
			"service", "order",
			"mode", string(m.mode),
			"symbol", string(o.Symbol),
			"order_id", o.ID,
			"signal_id", key,
			"err", err.Error(),
		)
		return domain.Order{}, fmt.Errorf("order: place: %w", err)
	}

	m.mu.Lock()
	m.seen[key] = placed
	m.mu.Unlock()

	slog.InfoContext(ctx, "order placed",
		"service", "order",
		"mode", string(m.mode),
		"symbol", string(placed.Symbol),
		"order_id", placed.ID,
		"signal_id", key,
		"qty", placed.Qty.String(),
		"price", placed.Price.String(),
		"status", string(placed.Status),
	)

	return placed, nil
}

func buildOrder(vs risk.ValidatedSignal, mode domain.Mode) domain.Order {
	now := timex.NowMs()
	return domain.Order{
		ID:        ids.New(),
		Symbol:    vs.Signal.Symbol,
		Side:      vs.Side,
		Type:      vs.OrderType,
		Qty:       vs.Qty,
		Price:     vs.Price,
		StopPrice: vs.StopLoss,
		Status:    domain.OrderStatusNew,
		Mode:      mode,
		CreatedMs: now,
		UpdatedMs: now,
	}
}
