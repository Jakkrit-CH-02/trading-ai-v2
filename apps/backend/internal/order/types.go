package order

import (
	"context"
	"errors"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// Sentinel errors. Callers use errors.Is to branch on rejection reason.
var (
	ErrLiveDisabled   = errors.New("order: live trading disabled")
	ErrUnknownMode    = errors.New("order: unknown execution mode")
	ErrModeUnsupported = errors.New("order: mode not yet supported")
)

// Executor places an order on a concrete execution backend (paper engine,
// Binance live, or backtest fill simulator). Implementations are responsible
// for setting fill details (Status, ExchangeID) on the returned Order.
type Executor interface {
	Place(ctx context.Context, o domain.Order) (domain.Order, error)
}
