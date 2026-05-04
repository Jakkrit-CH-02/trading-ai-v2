package tradelog

import (
	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

// Record is one row in the trade log: a fill (or signal-only event with zero
// qty) plus its surrounding context — strategy reason, AI confidence, P&L.
type Record struct {
	ID            string          `json:"id"`
	Mode          domain.Mode     `json:"mode"`
	Symbol        domain.Symbol   `json:"symbol"`
	Side          domain.Side     `json:"side"`
	OrderID       string          `json:"order_id"`
	SignalID      string          `json:"signal_id"`
	Strategy      string          `json:"strategy"`
	Reason        string          `json:"reason"`
	AIConfidence  decimal.Decimal `json:"ai_confidence"`
	Qty           decimal.Decimal `json:"qty"`
	FillPrice     decimal.Decimal `json:"fill_price"`
	Fee           decimal.Decimal `json:"fee"`
	RealizedPL    decimal.Decimal `json:"realized_pl"`
	CashAfter     decimal.Decimal `json:"cash_after"`
	TimestampMs   int64           `json:"timestamp_ms"`
}

// Filter constrains a List query. Zero values mean "no constraint".
type Filter struct {
	Mode      domain.Mode
	Symbol    domain.Symbol
	Side      domain.Side
	Strategy  string
	FromMs    int64
	ToMs      int64
	Limit     int
	Offset    int
}

// Period selects the rolling window used by Summary.
type Period string

const (
	PeriodDay  Period = "day"
	PeriodWeek Period = "week"
	PeriodAll  Period = "all"
)

// Summary aggregates a Period of trade records.
type Summary struct {
	Period         Period          `json:"period"`
	FromMs         int64           `json:"from_ms"`
	ToMs           int64           `json:"to_ms"`
	Count          int             `json:"count"`
	BuyCount       int             `json:"buy_count"`
	SellCount      int             `json:"sell_count"`
	GrossVolume    decimal.Decimal `json:"gross_volume"`
	RealizedPL     decimal.Decimal `json:"realized_pl"`
	TotalFees      decimal.Decimal `json:"total_fees"`
	WinningTrades  int             `json:"winning_trades"`
	LosingTrades   int             `json:"losing_trades"`
}
