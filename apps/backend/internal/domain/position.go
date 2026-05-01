package domain

import "github.com/shopspring/decimal"

// Position is the net exposure on a symbol.
type Position struct {
	Symbol       Symbol          `json:"symbol"`
	Qty          decimal.Decimal `json:"qty"`
	AvgEntry     decimal.Decimal `json:"avg_entry"`
	UnrealizedPL decimal.Decimal `json:"unrealized_pl"`
	RealizedPL   decimal.Decimal `json:"realized_pl"`
	UpdatedMs    int64           `json:"updated_ms"`
}
