package domain

import "github.com/shopspring/decimal"

// Position is the net exposure on a symbol.
// Side == SideBuy means long; Side == SideSell means short.
// Zero-value Side is treated as SideBuy (long) for backwards compatibility.
type Position struct {
	Symbol       Symbol          `json:"symbol"`
	Side         Side            `json:"side"`
	Qty          decimal.Decimal `json:"qty"`
	AvgEntry     decimal.Decimal `json:"avg_entry"`
	UnrealizedPL decimal.Decimal `json:"unrealized_pl"`
	RealizedPL   decimal.Decimal `json:"realized_pl"`
	UpdatedMs    int64           `json:"updated_ms"`

	// Exit management fields. Set when the position is opened; updated each bar.
	StopLoss           decimal.Decimal `json:"stop_loss"`            // current SL level
	TakeProfit         decimal.Decimal `json:"take_profit"`          // fixed TP; zero = disabled
	TrailHigh          decimal.Decimal `json:"trail_high"`           // highest price since trail activated (longs)
	TrailLow           decimal.Decimal `json:"trail_low"`            // lowest price since trail activated (shorts)
	TrailActivationPct decimal.Decimal `json:"trail_activation_pct"` // profit % at which trail kicks in
	TrailPct           decimal.Decimal `json:"trail_pct"`            // trail distance from extreme
}
