package domain

import "github.com/shopspring/decimal"

type SignalAction string

const (
	SignalActionBuy  SignalAction = "buy"
	SignalActionSell SignalAction = "sell"
	SignalActionHold SignalAction = "hold"
)

// Signal is the output of a strategy on a single bar.
type Signal struct {
	ID        string          `json:"id"`
	Symbol    Symbol          `json:"symbol"`
	Action    SignalAction    `json:"action"`
	Strength  decimal.Decimal `json:"strength"`
	Reason    string          `json:"reason"`
	Strategy  string          `json:"strategy"`
	CreatedMs int64           `json:"created_ms"`
}
