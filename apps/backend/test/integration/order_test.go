package integration

import (
	"context"
	"errors"
	"sync"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
)

// mockPaperEngine is a stand-in for paper.Engine — captures every order it
// receives and stamps a fill so the manager sees a non-trivial result.
type mockPaperEngine struct {
	mu       sync.Mutex
	received []domain.Order
}

func (m *mockPaperEngine) Place(_ context.Context, o domain.Order) (domain.Order, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.received = append(m.received, o)
	o.Status = domain.OrderStatusFilled
	o.ExchangeID = "paper-" + o.ID
	return o, nil
}

func (m *mockPaperEngine) calls() []domain.Order {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]domain.Order, len(m.received))
	copy(out, m.received)
	return out
}

func makeValidatedSignal(t *testing.T, signalID string) risk.ValidatedSignal {
	t.Helper()
	return risk.ValidatedSignal{
		Proposal: risk.Proposal{
			Signal: domain.Signal{
				ID:       signalID,
				Symbol:   domain.Symbol("BTCUSDT"),
				Action:   domain.SignalActionBuy,
				Strategy: "ma-cross",
			},
			Side:      domain.SideBuy,
			OrderType: domain.OrderTypeMarket,
			Qty:       decimal.NewFromFloat(0.001),
			Price:     decimal.NewFromInt(50_000),
			StopLoss:  decimal.NewFromInt(49_000),
			Equity:    decimal.NewFromInt(10_000),
		},
		ValidatedMs: 1,
	}
}

func TestOrderManager_PaperModeRoutesToPaperEngine(t *testing.T) {
	paper := &mockPaperEngine{}
	router := order.NewRouter(paper, nil)
	mgr := order.NewManager(router, domain.ModePaper)

	vs := makeValidatedSignal(t, "sig-01")
	placed, err := mgr.Submit(context.Background(), vs)

	require.NoError(t, err)
	require.Equal(t, domain.OrderStatusFilled, placed.Status)
	require.Equal(t, domain.ModePaper, placed.Mode)
	require.Equal(t, vs.Signal.Symbol, placed.Symbol)
	require.True(t, placed.Qty.Equal(vs.Qty), "qty preserved")
	require.True(t, placed.Price.Equal(vs.Price), "price preserved")
	require.True(t, placed.StopPrice.Equal(vs.StopLoss), "stop loss copied")
	require.NotEmpty(t, placed.ID)
	require.NotEmpty(t, placed.ExchangeID)

	calls := paper.calls()
	require.Len(t, calls, 1, "paper engine received exactly one order")
	require.Equal(t, vs.Signal.Symbol, calls[0].Symbol)
	require.Equal(t, domain.OrderStatusNew, calls[0].Status, "manager hands off as 'new' before fill")
}

func TestOrderManager_IdempotentOnRepeatedSignal(t *testing.T) {
	paper := &mockPaperEngine{}
	mgr := order.NewManager(order.NewRouter(paper, nil), domain.ModePaper)

	vs := makeValidatedSignal(t, "sig-dupe")

	first, err := mgr.Submit(context.Background(), vs)
	require.NoError(t, err)

	second, err := mgr.Submit(context.Background(), vs)
	require.NoError(t, err)

	require.Equal(t, first.ID, second.ID, "same signal -> same order id")
	require.Len(t, paper.calls(), 1, "executor invoked only once")
}

func TestOrderManager_LiveModeDisabledUntilSprint7(t *testing.T) {
	paper := &mockPaperEngine{}
	mgr := order.NewManager(order.NewRouter(paper, nil), domain.ModeLive)

	_, err := mgr.Submit(context.Background(), makeValidatedSignal(t, "sig-live"))
	require.Error(t, err)
	require.True(t, errors.Is(err, order.ErrLiveDisabled), "expected ErrLiveDisabled, got %v", err)
	require.Empty(t, paper.calls(), "paper engine must not see live orders")
}

func TestOrderManager_BacktestModeUnsupportedUntilHooked(t *testing.T) {
	mgr := order.NewManager(order.NewRouter(&mockPaperEngine{}, nil), domain.ModeBacktest)

	_, err := mgr.Submit(context.Background(), makeValidatedSignal(t, "sig-bt"))
	require.Error(t, err)
	require.True(t, errors.Is(err, order.ErrModeUnsupported))
}

func TestOrderManager_RejectsMissingSignalID(t *testing.T) {
	mgr := order.NewManager(order.NewRouter(&mockPaperEngine{}, nil), domain.ModePaper)

	vs := makeValidatedSignal(t, "")
	_, err := mgr.Submit(context.Background(), vs)
	require.Error(t, err)
}
