package runtime

import (
	"context"
	"fmt"
	"log/slog"
	"strings"
	"sync"
	"time"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/binance"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/paper"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy/builtin"
)

const startupWarmupBars = 64

// TradeRecord is a filled paper order stored for history.
type TradeRecord struct {
	OrderID     string `json:"order_id"`
	Symbol      string `json:"symbol"`
	Side        string `json:"side"`
	Qty         string `json:"qty"`
	FillPrice   string `json:"fill_price"`
	RealizedPL  string `json:"realized_pl"`
	Cash        string `json:"cash"`
	TimestampMs int64  `json:"timestamp_ms"`
}

// EquityPoint is a point on the equity curve.
type EquityPoint struct {
	TimestampMs int64  `json:"timestamp_ms"`
	Equity      string `json:"equity"`
}

// PerformanceSummary aggregates trade statistics.
type PerformanceSummary struct {
	TotalTrades     int     `json:"total_trades"`
	WinTrades       int     `json:"win_trades"`
	LossTrades      int     `json:"loss_trades"`
	WinRate         float64 `json:"win_rate"`
	TotalRealizedPL string  `json:"total_realized_pl"`
}

// PortfolioSnapshot is the current paper portfolio state.
type PortfolioSnapshot struct {
	InitialBalance string              `json:"initial_balance"`
	Cash           string              `json:"cash"`
	Equity         string              `json:"equity"`
	RealizedPL     string              `json:"realized_pl"`
	UnrealizedPL   string              `json:"unrealized_pl"`
	Positions      []domain.Position   `json:"positions"`
	EquityCurve    []EquityPoint        `json:"equity_curve"`
	Performance    PerformanceSummary  `json:"performance"`
	UpdatedMs      int64               `json:"updated_ms"`
}

// StartRequest holds validated parameters for Manager.Start.
type StartRequest struct {
	Mode             domain.Mode
	Strategy         string
	Symbol           domain.Symbol
	Timeframe        string
	MaxPositionPct   decimal.Decimal
	MaxDailyDrawdown decimal.Decimal
	MaxSlippageBps   int
	StopLossFraction decimal.Decimal
}

// Manager owns the lifecycle of a paper-trading session: bar feed, pipeline,
// controller, and accumulated state (trades, equity curve).
type Manager struct {
	binanceCfg binance.Config

	mu          sync.Mutex
	eng         *paper.Engine
	ctrl        *Controller
	cancelFeed  context.CancelFunc
	trades      []TradeRecord
	equityCurve []EquityPoint
	initial     decimal.Decimal
	totalPL     decimal.Decimal
	winTrades   int
	lossTrades  int
	mode        domain.Mode
	symbol      domain.Symbol
}

// NewManager constructs an idle Manager with a 10 000 USDT paper balance.
func NewManager(binanceCfg binance.Config) *Manager {
	init := decimal.NewFromInt(10_000)
	return &Manager{
		binanceCfg:  binanceCfg,
		initial:     init,
		equityCurve: []EquityPoint{{TimestampMs: timex.NowMs(), Equity: init.StringFixed(2)}},
		mode:        domain.ModePaper,
	}
}

// Start builds and starts the paper trading pipeline with the given config.
// Returns ErrAlreadyRunning when already running, ErrHalted when halted.
func (m *Manager) Start(ctx context.Context, req StartRequest) error {
	m.mu.Lock()
	defer m.mu.Unlock()

	if m.ctrl != nil {
		switch m.ctrl.State() {
		case StateRunning:
			return ErrAlreadyRunning
		case StateHalted:
			return ErrHalted
		}
	}

	strat, err := buildStrategy(req.Strategy)
	if err != nil {
		return err
	}

	eng := paper.NewEngine(m.initial)

	rsk := risk.NewEngine(risk.Policy{
		MaxPositionPct:      req.MaxPositionPct,
		MaxDailyDrawdownPct: req.MaxDailyDrawdown,
		MaxSlippageBps:      req.MaxSlippageBps,
		RequireStopLoss:     true,
	})

	mgr := order.NewManager(order.NewRouter(eng, nil), req.Mode)

	sizer := FixedFractionSizer(PipelineConfig{
		PositionFraction: req.MaxPositionPct,
		StopLossFraction: req.StopLossFraction,
	})

	pipe := NewPipeline(strategy.NewEngine(strat), rsk, mgr, eng, eng, eng, sizer)

	binClient := binance.New(m.binanceCfg)
	if err := m.warmPipeline(ctx, binClient, pipe, req); err != nil {
		slog.WarnContext(ctx, "runtime warmup failed; continuing with live stream only",
			"service", "runtime",
			"mode", string(req.Mode),
			"symbol", string(req.Symbol),
			"strategy", req.Strategy,
			"timeframe", req.Timeframe,
			"err", err.Error(),
		)
	}
	feedCtx, cancelFeed := context.WithCancel(context.Background())
	bars := binClient.KlineStream(feedCtx, req.Symbol, req.Timeframe)

	ctrl := NewController(pipe, bars, req.Mode, req.Symbol).WithFlattener(eng)
	if err := ctrl.Start(ctx); err != nil {
		cancelFeed()
		return err
	}

	m.eng = eng
	m.ctrl = ctrl
	m.cancelFeed = cancelFeed
	m.mode = req.Mode
	m.symbol = req.Symbol
	m.trades = nil
	m.totalPL = decimal.Zero
	m.winTrades = 0
	m.lossTrades = 0
	m.equityCurve = []EquityPoint{{TimestampMs: timex.NowMs(), Equity: m.initial.StringFixed(2)}}

	go m.drainEvents(feedCtx, eng.Events())
	go m.snapshotEquity(feedCtx, eng)

	slog.InfoContext(ctx, "manager started paper session",
		"service", "runtime",
		"mode", string(req.Mode),
		"symbol", string(req.Symbol),
		"strategy", req.Strategy,
		"timeframe", req.Timeframe,
	)
	return nil
}

func (m *Manager) warmPipeline(ctx context.Context, cl *binance.Client, pipe *Pipeline, req StartRequest) error {
	bars, err := cl.GetKlines(ctx, binance.KlinesQuery{
		Symbol:   string(req.Symbol),
		Interval: req.Timeframe,
		Limit:    startupWarmupBars,
	})
	if err != nil {
		return err
	}
	if len(bars) == 0 {
		return fmt.Errorf("binance warmup returned no candles")
	}
	if err := pipe.Warm(ctx, bars); err != nil {
		return err
	}

	last := pipe.LastSignal()
	slog.InfoContext(ctx, "runtime warmup complete",
		"service", "runtime",
		"mode", string(req.Mode),
		"symbol", string(req.Symbol),
		"strategy", req.Strategy,
		"timeframe", req.Timeframe,
		"bars", len(bars),
		"last_signal_action", string(last.Action),
		"last_signal_reason", last.Reason,
	)
	return nil
}

// Stop stops the running bot and the bar feed.
func (m *Manager) Stop(ctx context.Context) error {
	m.mu.Lock()
	ctrl := m.ctrl
	cancelFeed := m.cancelFeed
	m.cancelFeed = nil
	m.mu.Unlock()

	if ctrl == nil {
		return ErrNotRunning
	}
	if cancelFeed != nil {
		cancelFeed()
	}
	return ctrl.Stop(ctx)
}

// Pause pauses the running bot.
func (m *Manager) Pause(ctx context.Context) error {
	m.mu.Lock()
	ctrl := m.ctrl
	m.mu.Unlock()
	if ctrl == nil {
		return ErrNotRunning
	}
	return ctrl.Pause(ctx)
}

// Kill engages the kill switch, flattens positions, and halts.
func (m *Manager) Kill(ctx context.Context) error {
	m.mu.Lock()
	ctrl := m.ctrl
	cancelFeed := m.cancelFeed
	m.cancelFeed = nil
	m.mu.Unlock()

	if cancelFeed != nil {
		cancelFeed()
	}
	if ctrl == nil {
		return nil
	}
	return ctrl.Kill(ctx)
}

// Reset moves the controller from halted → idle so the bot can restart.
func (m *Manager) Reset(ctx context.Context) error {
	m.mu.Lock()
	ctrl := m.ctrl
	m.mu.Unlock()
	if ctrl == nil {
		return fmt.Errorf("runtime: not halted")
	}
	return ctrl.Reset(ctx)
}

// BotStatus returns the current bot status for GET /api/bot/status.
func (m *Manager) BotStatus() Status {
	m.mu.Lock()
	ctrl := m.ctrl
	mode := m.mode
	symbol := m.symbol
	m.mu.Unlock()

	if ctrl == nil {
		return Status{State: StateIdle, Mode: mode, Symbol: symbol}
	}
	return ctrl.Status()
}

// Portfolio returns the current paper portfolio snapshot.
func (m *Manager) Portfolio() PortfolioSnapshot {
	m.mu.Lock()
	eng := m.eng
	initial := m.initial
	curve := make([]EquityPoint, len(m.equityCurve))
	copy(curve, m.equityCurve)
	totalPL := m.totalPL
	winTrades := m.winTrades
	lossTrades := m.lossTrades
	totalTrades := winTrades + lossTrades
	m.mu.Unlock()

	if eng == nil {
		return PortfolioSnapshot{
			InitialBalance: initial.StringFixed(2),
			Cash:           initial.StringFixed(2),
			Equity:         initial.StringFixed(2),
			RealizedPL:     "0.00",
			UnrealizedPL:   "0.00",
			Positions:      []domain.Position{},
			EquityCurve:    curve,
			Performance:    PerformanceSummary{TotalRealizedPL: "0.00"},
			UpdatedMs:      timex.NowMs(),
		}
	}

	eq := eng.Equity()
	cash := eng.Cash()
	positions := eng.Positions()

	unrealizedPL := decimal.Zero
	for _, p := range positions {
		unrealizedPL = unrealizedPL.Add(p.UnrealizedPL)
	}
	if positions == nil {
		positions = []domain.Position{}
	}

	winRate := 0.0
	if totalTrades > 0 {
		winRate = float64(winTrades) / float64(totalTrades)
	}

	return PortfolioSnapshot{
		InitialBalance: initial.StringFixed(2),
		Cash:           cash.StringFixed(2),
		Equity:         eq.StringFixed(2),
		RealizedPL:     totalPL.StringFixed(2),
		UnrealizedPL:   unrealizedPL.StringFixed(2),
		Positions:      positions,
		EquityCurve:    curve,
		Performance: PerformanceSummary{
			TotalTrades:     totalTrades,
			WinTrades:       winTrades,
			LossTrades:      lossTrades,
			WinRate:         winRate,
			TotalRealizedPL: totalPL.StringFixed(2),
		},
		UpdatedMs: timex.NowMs(),
	}
}

// Trades returns the accumulated paper fill history.
func (m *Manager) Trades() []TradeRecord {
	m.mu.Lock()
	t := make([]TradeRecord, len(m.trades))
	copy(t, m.trades)
	m.mu.Unlock()
	return t
}

// InjectBar sends a synthetic bar into the running pipeline and waits for the
// resulting signal. For dev/test use only.
func (m *Manager) InjectBar(ctx context.Context, b domain.Bar) (domain.Signal, error) {
	m.mu.Lock()
	ctrl := m.ctrl
	m.mu.Unlock()
	if ctrl == nil {
		return domain.Signal{}, fmt.Errorf("runtime: bot is not started")
	}
	return ctrl.InjectBarSync(ctx, b)
}

// ResetPortfolio resets the paper portfolio to its initial state.
func (m *Manager) ResetPortfolio() {
	m.mu.Lock()
	defer m.mu.Unlock()
	m.trades = nil
	m.totalPL = decimal.Zero
	m.winTrades = 0
	m.lossTrades = 0
	m.equityCurve = []EquityPoint{{TimestampMs: timex.NowMs(), Equity: m.initial.StringFixed(2)}}
	if m.eng != nil {
		m.eng.Reset()
	}
}

func (m *Manager) drainEvents(ctx context.Context, ch <-chan paper.TradeLogEvent) {
	for {
		select {
		case <-ctx.Done():
			return
		case evt, ok := <-ch:
			if !ok {
				return
			}
			tr := TradeRecord{
				OrderID:     evt.OrderID,
				Symbol:      string(evt.Symbol),
				Side:        string(evt.Side),
				Qty:         evt.Qty.StringFixed(6),
				FillPrice:   evt.FillPrice.StringFixed(2),
				RealizedPL:  evt.RealizedPL.StringFixed(2),
				Cash:        evt.Cash.StringFixed(2),
				TimestampMs: evt.TimestampMs,
			}
			m.mu.Lock()
			m.trades = append(m.trades, tr)
			m.totalPL = m.totalPL.Add(evt.RealizedPL)
			if evt.RealizedPL.IsPositive() {
				m.winTrades++
			} else if evt.RealizedPL.IsNegative() {
				m.lossTrades++
			}
			m.mu.Unlock()
		}
	}
}

func (m *Manager) snapshotEquity(ctx context.Context, eng *paper.Engine) {
	tick := time.NewTicker(5 * time.Second)
	defer tick.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-tick.C:
			eq := eng.Equity()
			pt := EquityPoint{TimestampMs: timex.NowMs(), Equity: eq.StringFixed(2)}
			m.mu.Lock()
			m.equityCurve = append(m.equityCurve, pt)
			m.mu.Unlock()
		}
	}
}

func buildStrategy(name string) (strategy.Strategy, error) {
	normalized := strings.ToLower(strings.ReplaceAll(strings.TrimSpace(name), " ", "_"))
	switch normalized {
	case "ma_crossover", "ma_cross", "ma_crossover_(9,21)":
		return builtin.NewMACross(9, 21), nil
	case "rsi", "rsi_(14)":
		return builtin.NewRSI(14, decimal.NewFromInt(30), decimal.NewFromInt(70)), nil
	default:
		return nil, fmt.Errorf("runtime: unknown strategy %q", name)
	}
}
