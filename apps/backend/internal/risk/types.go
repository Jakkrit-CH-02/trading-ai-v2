package risk

import (
	"errors"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// Sentinel errors. Callers use errors.Is to branch on rejection reason.
var (
	ErrPositionTooLarge = errors.New("risk: position exceeds max position pct")
	ErrDailyDrawdown    = errors.New("risk: daily drawdown limit reached")
	ErrStopLossRequired = errors.New("risk: stop loss required")
	ErrSlippageExceeded = errors.New("risk: slippage exceeds max bps")
)

// Proposal is the candidate order presented to the risk engine for validation.
// It carries everything the engine needs to make a pure decision: no I/O.
type Proposal struct {
	Signal      domain.Signal
	Side        domain.Side
	OrderType   domain.OrderType
	Qty         decimal.Decimal
	Price       decimal.Decimal
	StopLoss    decimal.Decimal
	Equity      decimal.Decimal
	DailyPnL    decimal.Decimal // realized + unrealized P&L for the current UTC day
	SlippageBps int             // expected slippage from book depth (market orders)
}

// ValidatedSignal is a Proposal that has passed every active risk check.
type ValidatedSignal struct {
	Proposal
	ValidatedMs int64
}
