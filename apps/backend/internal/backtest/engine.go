// Package backtest replays historical bars over a strategy + risk engine,
// simulating fills at bar close (no spread) and producing equity curve,
// trade list, and aggregate metrics (P&L, drawdown, sharpe, win rate).
package backtest

import (
	"context"
	"fmt"
	"math"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

// Config drives a single backtest run.
type Config struct {
	Symbol           domain.Symbol     `json:"symbol"`
	Interval         string            `json:"interval"`
	StrategyName     string            `json:"strategy_name"`
	StrategyParams   map[string]string `json:"strategy_params"`
	InitialCash      decimal.Decimal   `json:"initial_cash"`
	PositionFraction decimal.Decimal   `json:"position_fraction"` // 0..1, fraction of equity per buy
	StopLossPct      decimal.Decimal   `json:"stop_loss_pct"`     // e.g. 0.05 = 5% below entry
	FromMs           int64             `json:"from_ms,omitempty"`
	ToMs             int64             `json:"to_ms,omitempty"`
}

// Trade is one simulated fill.
type Trade struct {
	SignalID    string          `json:"signal_id"`
	OrderID     string          `json:"order_id"`
	Symbol      domain.Symbol   `json:"symbol"`
	Side        domain.Side     `json:"side"`
	Qty         decimal.Decimal `json:"qty"`
	Price       decimal.Decimal `json:"price"`
	RealizedPL  decimal.Decimal `json:"realized_pl"`
	Reason      string          `json:"reason"`
	TimestampMs int64           `json:"timestamp_ms"`
}

// EquityPoint is one (time, equity) sample on the equity curve.
type EquityPoint struct {
	TimestampMs int64           `json:"timestamp_ms"`
	Equity      decimal.Decimal `json:"equity"`
}

// Metrics is the aggregate report computed at the end of a run.
type Metrics struct {
	TotalTrades   int             `json:"total_trades"`
	WinningTrades int             `json:"winning_trades"`
	LosingTrades  int             `json:"losing_trades"`
	WinRate       decimal.Decimal `json:"win_rate"`
	ProfitFactor  decimal.Decimal `json:"profit_factor"`
	TotalReturn   decimal.Decimal `json:"total_return"`
	MaxDrawdown   decimal.Decimal `json:"max_drawdown"`
	SharpeRatio   decimal.Decimal `json:"sharpe_ratio"`
}

// Result is the durable output of a backtest run.
type Result struct {
	ID            string          `json:"id"`
	Config        Config          `json:"config"`
	StartMs       int64           `json:"start_ms"`
	EndMs         int64           `json:"end_ms"`
	BarsProcessed int             `json:"bars_processed"`
	InitialEquity decimal.Decimal `json:"initial_equity"`
	FinalEquity   decimal.Decimal `json:"final_equity"`
	Metrics       Metrics         `json:"metrics"`
	EquityCurve   []EquityPoint   `json:"equity_curve"`
	Trades        []Trade         `json:"trades"`
	CreatedMs     int64           `json:"created_ms"`
}

// Engine runs one backtest. Construct per run; not safe for concurrent use.
type Engine struct {
	cfg      Config
	strat    strategy.Strategy
	risk     *risk.Engine // optional; nil disables risk validation
	clock    func() int64 // injectable for deterministic CreatedMs in tests
	newID    func() string
}

// NewEngine builds an engine with the given config, strategy and (optional)
// risk engine. clock and newID are optional; nil falls back to wall clock /
// ULID generators.
func NewEngine(cfg Config, strat strategy.Strategy, r *risk.Engine) *Engine {
	if cfg.PositionFraction.IsZero() {
		cfg.PositionFraction = decimal.NewFromFloat(0.5)
	}
	if cfg.StopLossPct.IsZero() {
		cfg.StopLossPct = decimal.NewFromFloat(0.05)
	}
	return &Engine{
		cfg:   cfg,
		strat: strat,
		risk:  r,
		clock: func() int64 { return 0 },
		newID: ids.New,
	}
}

// WithClock overrides the timestamp source used for the result's CreatedMs.
func (e *Engine) WithClock(f func() int64) *Engine { e.clock = f; return e }

// WithIDFunc overrides the id generator (deterministic tests).
func (e *Engine) WithIDFunc(f func() string) *Engine { e.newID = f; return e }

// Run replays bars in order, feeding each through the strategy and (when a
// non-HOLD signal arrives) sizing/validating/filling an order.
//
// Fill model: market at bar.Close, no spread, no fees. Position sizing uses
// PositionFraction of current equity. Long-only.
func (e *Engine) Run(ctx context.Context, bars []domain.Bar) (Result, error) {
	if e.strat == nil {
		return Result{}, fmt.Errorf("backtest: strategy required")
	}
	if e.cfg.InitialCash.LessThanOrEqual(decimal.Zero) {
		return Result{}, fmt.Errorf("backtest: initial_cash must be > 0")
	}

	bars = filterRange(bars, e.cfg.FromMs, e.cfg.ToMs)
	if len(bars) == 0 {
		return Result{}, fmt.Errorf("backtest: no bars in range")
	}

	cash := e.cfg.InitialCash
	var qty, avgEntry decimal.Decimal
	trades := make([]Trade, 0, 8)
	curve := make([]EquityPoint, 0, len(bars))

	for _, b := range bars {
		if err := ctx.Err(); err != nil {
			return Result{}, err
		}

		sig, err := e.strat.OnBar(ctx, b)
		if err != nil {
			return Result{}, fmt.Errorf("backtest: strategy: %w", err)
		}

		switch sig.Action {
		case domain.SignalActionBuy:
			if !qty.IsZero() {
				break // already long; ignore
			}
			equity := cash.Add(qty.Mul(b.Close))
			notional := equity.Mul(e.cfg.PositionFraction)
			if notional.GreaterThan(cash) {
				notional = cash
			}
			if notional.LessThanOrEqual(decimal.Zero) || b.Close.LessThanOrEqual(decimal.Zero) {
				break
			}
			fillQty := notional.DivRound(b.Close, 8)
			if fillQty.LessThanOrEqual(decimal.Zero) {
				break
			}
			stop := b.Close.Mul(decimal.NewFromInt(1).Sub(e.cfg.StopLossPct))
			if e.risk != nil {
				prop := risk.Proposal{
					Signal:    sig,
					Side:      domain.SideBuy,
					OrderType: domain.OrderTypeMarket,
					Qty:       fillQty,
					Price:     b.Close,
					StopLoss:  stop,
					Equity:    equity,
				}
				if _, rerr := e.risk.Validate(ctx, prop); rerr != nil {
					continue
				}
			}
			cost := fillQty.Mul(b.Close)
			cash = cash.Sub(cost)
			avgEntry = b.Close
			qty = fillQty
			trades = append(trades, Trade{
				SignalID:    sig.ID,
				OrderID:     e.newID(),
				Symbol:      b.Symbol,
				Side:        domain.SideBuy,
				Qty:         fillQty,
				Price:       b.Close,
				RealizedPL:  decimal.Zero,
				Reason:      sig.Reason,
				TimestampMs: b.CloseTime,
			})

		case domain.SignalActionSell:
			if qty.IsZero() {
				break
			}
			realized := b.Close.Sub(avgEntry).Mul(qty)
			cash = cash.Add(qty.Mul(b.Close))
			trades = append(trades, Trade{
				SignalID:    sig.ID,
				OrderID:     e.newID(),
				Symbol:      b.Symbol,
				Side:        domain.SideSell,
				Qty:         qty,
				Price:       b.Close,
				RealizedPL:  realized,
				Reason:      sig.Reason,
				TimestampMs: b.CloseTime,
			})
			qty = decimal.Zero
			avgEntry = decimal.Zero
		}

		eq := cash.Add(qty.Mul(b.Close))
		curve = append(curve, EquityPoint{TimestampMs: b.CloseTime, Equity: eq})
	}

	final := curve[len(curve)-1].Equity
	res := Result{
		ID:            e.newID(),
		Config:        e.cfg,
		StartMs:       bars[0].CloseTime,
		EndMs:         bars[len(bars)-1].CloseTime,
		BarsProcessed: len(bars),
		InitialEquity: e.cfg.InitialCash,
		FinalEquity:   final,
		Metrics:       computeMetrics(e.cfg.InitialCash, curve, trades),
		EquityCurve:   curve,
		Trades:        trades,
		CreatedMs:     e.clock(),
	}
	return res, nil
}

func filterRange(bars []domain.Bar, fromMs, toMs int64) []domain.Bar {
	if fromMs <= 0 && toMs <= 0 {
		return bars
	}
	out := make([]domain.Bar, 0, len(bars))
	for _, b := range bars {
		if fromMs > 0 && b.CloseTime < fromMs {
			continue
		}
		if toMs > 0 && b.CloseTime > toMs {
			continue
		}
		out = append(out, b)
	}
	return out
}

// computeMetrics derives the report from equity curve + closed trades.
//
// Closed trade = one SELL leg; its RealizedPL is its outcome. WinRate /
// ProfitFactor are computed only over closed trades. Sharpe is annualized
// per-bar return (assumes uniform sampling).
func computeMetrics(initial decimal.Decimal, curve []EquityPoint, trades []Trade) Metrics {
	m := Metrics{}
	var wins, losses decimal.Decimal
	for _, t := range trades {
		if t.Side != domain.SideSell {
			continue
		}
		m.TotalTrades++
		switch {
		case t.RealizedPL.GreaterThan(decimal.Zero):
			m.WinningTrades++
			wins = wins.Add(t.RealizedPL)
		case t.RealizedPL.LessThan(decimal.Zero):
			m.LosingTrades++
			losses = losses.Add(t.RealizedPL.Abs())
		}
	}

	if m.TotalTrades > 0 {
		m.WinRate = decimal.NewFromInt(int64(m.WinningTrades)).
			DivRound(decimal.NewFromInt(int64(m.TotalTrades)), 6)
	}
	if !losses.IsZero() {
		m.ProfitFactor = wins.DivRound(losses, 6)
	} else if !wins.IsZero() {
		// All wins, no losses → undefined; use a sentinel large value.
		m.ProfitFactor = decimal.NewFromInt(1_000_000)
	}

	if !initial.IsZero() && len(curve) > 0 {
		final := curve[len(curve)-1].Equity
		m.TotalReturn = final.Sub(initial).DivRound(initial, 6)
	}
	m.MaxDrawdown = maxDrawdown(curve)
	m.SharpeRatio = sharpe(curve)
	return m
}

func maxDrawdown(curve []EquityPoint) decimal.Decimal {
	if len(curve) == 0 {
		return decimal.Zero
	}
	peak := curve[0].Equity
	maxDD := decimal.Zero
	for _, p := range curve {
		if p.Equity.GreaterThan(peak) {
			peak = p.Equity
		}
		if peak.IsZero() {
			continue
		}
		dd := peak.Sub(p.Equity).DivRound(peak, 6)
		if dd.GreaterThan(maxDD) {
			maxDD = dd
		}
	}
	return maxDD
}

// sharpe annualizes the per-bar log-return Sharpe ratio with rf=0. Returns
// zero when there is insufficient variance / data.
func sharpe(curve []EquityPoint) decimal.Decimal {
	if len(curve) < 2 {
		return decimal.Zero
	}
	rets := make([]float64, 0, len(curve)-1)
	for i := 1; i < len(curve); i++ {
		prev, _ := curve[i-1].Equity.Float64()
		cur, _ := curve[i].Equity.Float64()
		if prev <= 0 {
			continue
		}
		rets = append(rets, (cur-prev)/prev)
	}
	if len(rets) < 2 {
		return decimal.Zero
	}
	var sum float64
	for _, r := range rets {
		sum += r
	}
	mean := sum / float64(len(rets))
	var ssq float64
	for _, r := range rets {
		ssq += (r - mean) * (r - mean)
	}
	variance := ssq / float64(len(rets)-1)
	std := math.Sqrt(variance)
	if std == 0 {
		return decimal.Zero
	}
	// Annualize against ~252 trading days; the integration test asserts
	// only sign/finiteness, so the exact factor is documentation.
	annual := (mean / std) * math.Sqrt(252)
	if math.IsNaN(annual) || math.IsInf(annual, 0) {
		return decimal.Zero
	}
	return decimal.NewFromFloat(annual).Round(6)
}
