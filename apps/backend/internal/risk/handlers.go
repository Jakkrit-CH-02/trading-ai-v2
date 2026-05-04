package risk

import (
	"encoding/json"
	"net/http"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
)

// RuntimeView exposes the slice of bot runtime state the risk snapshot needs.
// The paper engine satisfies this directly; in live/backtest a thin adapter
// over the executor will provide the same surface.
type RuntimeView interface {
	Equity() decimal.Decimal
	Balance() decimal.Decimal
	Positions() []domain.Position
}

// StateFn returns the current bot FSM state (e.g. "idle", "running", "halted").
// Provided as a function to avoid an import cycle with internal/runtime.
type StateFn func() string

// Snapshot is the JSON payload returned by GET /api/risk/snapshot.
// Decimal fields are encoded as strings per the money convention.
type Snapshot struct {
	State                string             `json:"state"`
	MaxPositionPct       string             `json:"max_position_pct"`
	MaxDailyDrawdownPct  string             `json:"max_daily_drawdown_pct"`
	MaxSlippageBps       int                `json:"max_slippage_bps"`
	Equity               string             `json:"equity"`
	InitialEquity        string             `json:"initial_equity"`
	Cash                 string             `json:"cash"`
	Exposure             string             `json:"exposure"`
	ExposurePct          string             `json:"exposure_pct"`
	DailyPnL             string             `json:"daily_pnl"`
	DailyDrawdownPct     string             `json:"daily_drawdown_pct"`
	OpenPositions        int                `json:"open_positions"`
	LargestPositionPct   string             `json:"largest_position_pct"`
	Positions            []PositionSnapshot `json:"positions"`
	UpdatedMs            int64              `json:"updated_ms"`
}

// PositionSnapshot is a stripped-down position view aimed at the risk page.
type PositionSnapshot struct {
	Symbol       domain.Symbol `json:"symbol"`
	Qty          string        `json:"qty"`
	AvgEntry     string        `json:"avg_entry"`
	NotionalPct  string        `json:"notional_pct"`
	UnrealizedPL string        `json:"unrealized_pl"`
	RealizedPL   string        `json:"realized_pl"`
}

// Handler serves the risk monitor HTTP surface.
type Handler struct {
	policy  Policy
	rv      RuntimeView
	stateFn StateFn
	initial decimal.Decimal
}

// NewHandler wires the snapshot endpoint. initialEquity is the baseline used
// to compute session/daily P&L until a per-day reset hook lands.
func NewHandler(policy Policy, rv RuntimeView, stateFn StateFn, initialEquity decimal.Decimal) *Handler {
	return &Handler{policy: policy, rv: rv, stateFn: stateFn, initial: initialEquity}
}

// Mount installs the snapshot route on a chi-style router.
func (h *Handler) Mount(r interface {
	Get(pattern string, handler http.HandlerFunc)
}) {
	r.Get("/api/risk/snapshot", h.Snapshot)
}

// Snapshot returns the current risk view derived from runtime state.
func (h *Handler) Snapshot(w http.ResponseWriter, _ *http.Request) {
	snap := h.build()
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(http.StatusOK)
	_ = json.NewEncoder(w).Encode(envelope{Data: snap})
}

func (h *Handler) build() Snapshot {
	equity := h.rv.Equity()
	cash := h.rv.Balance()
	exposure := equity.Sub(cash)

	positions := h.rv.Positions()
	out := make([]PositionSnapshot, 0, len(positions))
	largestPct := decimal.Zero
	for _, p := range positions {
		notional := p.Qty.Mul(p.AvgEntry).Add(p.UnrealizedPL).Abs()
		pct := decimal.Zero
		if equity.GreaterThan(decimal.Zero) {
			pct = notional.Div(equity)
		}
		if pct.GreaterThan(largestPct) {
			largestPct = pct
		}
		out = append(out, PositionSnapshot{
			Symbol:       p.Symbol,
			Qty:          p.Qty.String(),
			AvgEntry:     p.AvgEntry.String(),
			NotionalPct:  pct.StringFixed(6),
			UnrealizedPL: p.UnrealizedPL.String(),
			RealizedPL:   p.RealizedPL.String(),
		})
	}

	pnl := equity.Sub(h.initial)
	dd := decimal.Zero
	if pnl.IsNegative() && h.initial.GreaterThan(decimal.Zero) {
		dd = pnl.Abs().Div(h.initial)
	}
	exposurePct := decimal.Zero
	if equity.GreaterThan(decimal.Zero) {
		exposurePct = exposure.Div(equity)
	}

	state := "idle"
	if h.stateFn != nil {
		state = h.stateFn()
	}

	return Snapshot{
		State:               state,
		MaxPositionPct:      h.policy.MaxPositionPct.String(),
		MaxDailyDrawdownPct: h.policy.MaxDailyDrawdownPct.String(),
		MaxSlippageBps:      h.policy.MaxSlippageBps,
		Equity:              equity.String(),
		InitialEquity:       h.initial.String(),
		Cash:                cash.String(),
		Exposure:            exposure.String(),
		ExposurePct:         exposurePct.StringFixed(6),
		DailyPnL:            pnl.String(),
		DailyDrawdownPct:    dd.StringFixed(6),
		OpenPositions:       len(positions),
		LargestPositionPct:  largestPct.StringFixed(6),
		Positions:           out,
		UpdatedMs:           timex.NowMs(),
	}
}

type envelope struct {
	Data  interface{} `json:"data"`
	Error *apiError   `json:"error"`
}

type apiError struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}
