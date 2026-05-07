package integration

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/audit"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/livegate"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/paper"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/runtime"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy/builtin"
)

func newMACrossEngine(t *testing.T) *strategy.Engine {
	t.Helper()
	return strategy.NewEngine(builtin.NewMACross(3, 5))
}

// stubLiveExec records orders the live executor receives — stand-in for
// the real Binance adapter so tests stay hermetic.
type stubLiveExec struct {
	mu       sync.Mutex
	received []domain.Order
}

func (s *stubLiveExec) Place(_ context.Context, o domain.Order) (domain.Order, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	s.received = append(s.received, o)
	o.Status = domain.OrderStatusFilled
	o.ExchangeID = "live-" + o.ID
	return o, nil
}

func (s *stubLiveExec) calls() int {
	s.mu.Lock()
	defer s.mu.Unlock()
	return len(s.received)
}

// liveSetup wires gate + audit + live executor into an order Manager.
type liveSetup struct {
	gate    *livegate.Gate
	audit   *audit.MemoryRepo
	upstream *stubLiveExec
	mgr     *order.Manager
}

type liveOpts struct {
	envEnabled bool
	apiOK      bool
	tokenTTL   time.Duration
}

func newLiveSetup(t *testing.T, opts liveOpts) *liveSetup {
	t.Helper()
	if opts.tokenTTL == 0 {
		opts.tokenTTL = 5 * time.Minute
	}
	gate := livegate.New(livegate.Config{
		EnvFlag:    func() bool { return opts.envEnabled },
		Permission: livegate.StaticPermission(opts.apiOK),
		TokenTTL:   opts.tokenTTL,
	})
	repo := audit.NewMemoryRepo()
	rec := audit.NewService(repo)
	upstream := &stubLiveExec{}
	live := order.NewLiveExecutor(gate, upstream, rec)
	router := order.NewRouter(nil, live)
	mgr := order.NewManager(router, domain.ModeLive)
	return &liveSetup{gate: gate, audit: repo, upstream: upstream, mgr: mgr}
}

func liveSignal(id string) risk.ValidatedSignal {
	return risk.ValidatedSignal{
		Proposal: risk.Proposal{
			Signal: domain.Signal{
				ID:       id,
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

func TestLiveGate_DeniesWhenEnvDisabled(t *testing.T) {
	s := newLiveSetup(t, liveOpts{envEnabled: false, apiOK: true})
	tok := s.gate.IssueToken(context.Background())

	ctx := livegate.WithToken(context.Background(), tok)
	_, err := s.mgr.Submit(ctx, liveSignal("sig-env"))

	require.Error(t, err)
	require.True(t, errors.Is(err, livegate.ErrEnvDisabled), "got %v", err)
	require.Equal(t, 0, s.upstream.calls(), "upstream must not be called on denial")

	rows := s.audit.Filter(audit.ActionLiveSubmit)
	require.Len(t, rows, 1, "denial must be audited")
	require.Contains(t, rows[0].Details, "denied=")
}

func TestLiveGate_DeniesWhenAPIPermissionsBad(t *testing.T) {
	s := newLiveSetup(t, liveOpts{envEnabled: true, apiOK: false})
	tok := s.gate.IssueToken(context.Background())

	ctx := livegate.WithToken(context.Background(), tok)
	_, err := s.mgr.Submit(ctx, liveSignal("sig-api"))

	require.Error(t, err)
	require.True(t, errors.Is(err, livegate.ErrAPIPermissions), "got %v", err)
	require.Equal(t, 0, s.upstream.calls())
	require.Len(t, s.audit.Filter(audit.ActionLiveSubmit), 1)
}

func TestLiveGate_DeniesWhenTokenMissing(t *testing.T) {
	s := newLiveSetup(t, liveOpts{envEnabled: true, apiOK: true})
	// No WithToken on ctx.
	_, err := s.mgr.Submit(context.Background(), liveSignal("sig-no-tok"))

	require.Error(t, err)
	require.True(t, errors.Is(err, livegate.ErrMissingToken), "got %v", err)
	require.Equal(t, 0, s.upstream.calls())
	require.Len(t, s.audit.Filter(audit.ActionLiveSubmit), 1)
}

func TestLiveGate_DeniesWhenTokenInvalid(t *testing.T) {
	s := newLiveSetup(t, liveOpts{envEnabled: true, apiOK: true})
	ctx := livegate.WithToken(context.Background(), "bogus-token")

	_, err := s.mgr.Submit(ctx, liveSignal("sig-bad-tok"))

	require.Error(t, err)
	require.True(t, errors.Is(err, livegate.ErrInvalidToken), "got %v", err)
	require.Equal(t, 0, s.upstream.calls())
}

func TestLiveGate_AllowsWhenAllConditionsMet_AuditRecorded(t *testing.T) {
	s := newLiveSetup(t, liveOpts{envEnabled: true, apiOK: true})
	tok := s.gate.IssueToken(context.Background())
	ctx := livegate.WithToken(order.WithActor(context.Background(), "alice"), tok)

	placed, err := s.mgr.Submit(ctx, liveSignal("sig-ok"))
	require.NoError(t, err)
	require.Equal(t, domain.OrderStatusFilled, placed.Status)
	require.Equal(t, 1, s.upstream.calls())

	rows := s.audit.Filter(audit.ActionLiveSubmit)
	require.Len(t, rows, 1)
	require.Equal(t, "alice", rows[0].Actor)
	require.Equal(t, string(domain.ModeLive), rows[0].Mode)
	require.Equal(t, placed.ID, rows[0].Entity)
	require.Contains(t, rows[0].Details, "status=filled")

	// Token is reusable within TTL — the active session may submit more orders.
	placed2, err := s.mgr.Submit(ctx, liveSignal("sig-ok-2"))
	require.NoError(t, err)
	require.Equal(t, 2, s.upstream.calls())
	require.Equal(t, 2, len(s.audit.Filter(audit.ActionLiveSubmit)))
	require.NotEqual(t, placed.ID, placed2.ID)
}

func TestLiveGate_TokenExpires(t *testing.T) {
	s := newLiveSetup(t, liveOpts{envEnabled: true, apiOK: true, tokenTTL: 1 * time.Millisecond})
	tok := s.gate.IssueToken(context.Background())
	time.Sleep(10 * time.Millisecond)

	ctx := livegate.WithToken(context.Background(), tok)
	_, err := s.mgr.Submit(ctx, liveSignal("sig-exp"))
	require.True(t, errors.Is(err, livegate.ErrInvalidToken), "got %v", err)
}

// --- Kill flow -------------------------------------------------------------

// killBars is the deterministic bar sequence used by the Kill test. Two
// rising bars seed the MA-crossover so the pipeline issues a BUY, leaving
// an open position the Kill must flatten.
func killBars(sym domain.Symbol) []domain.Bar {
	bars := make([]domain.Bar, 0, 16)
	t0 := int64(1_700_000_000_000)
	prices := []float64{
		100, 100, 100, 100, 100, 100,
		102, 105, 109, 114, 120, 127, 135,
	}
	for i, p := range prices {
		px := decimal.NewFromFloat(p)
		bars = append(bars, domain.Bar{
			Symbol:    sym,
			Interval:  "1m",
			OpenTime:  t0 + int64(i)*60_000,
			CloseTime: t0 + int64(i+1)*60_000 - 1,
			Open:      px,
			High:      px,
			Low:       px,
			Close:     px,
			Volume:    decimal.NewFromInt(1),
		})
	}
	return bars
}

func TestKill_FlattensPositions_RecordsAudit(t *testing.T) {
	// Build a paper-mode controller, run bars to open a position, then Kill.
	c, bars, eng := newKillSetup(t)

	require.NoError(t, c.Start(context.Background()))
	for _, b := range killBars(domain.Symbol("BTCUSDT")) {
		bars <- b
	}

	// Wait for the engine to actually hold an open position from the buy.
	require.Eventually(t, func() bool {
		for _, p := range eng.Positions() {
			if p.Qty.Sign() > 0 {
				return true
			}
		}
		return false
	}, 2*time.Second, 5*time.Millisecond, "expected an open paper position before Kill")

	repo := c.AuditRepo // helper field set by newKillSetup
	beforeRows := len(repo.Filter(audit.ActionKill))

	require.NoError(t, c.Kill(runtime.WithActor(context.Background(), "kill-operator")))
	require.Equal(t, runtime.StateHalted, c.State())

	// Positions must be flat after Kill.
	require.Empty(t, eng.Positions(), "Kill must flatten all positions")

	// Audit must record exactly one new kill row, attributed to the actor.
	rows := repo.Filter(audit.ActionKill)
	require.Equal(t, beforeRows+1, len(rows))
	require.Equal(t, "kill-operator", rows[len(rows)-1].Actor)

	// Halt locks out Start until Reset.
	require.ErrorIs(t, c.Start(context.Background()), runtime.ErrHalted)
	require.NoError(t, c.Reset(runtime.WithActor(context.Background(), "admin")))
	require.Equal(t, runtime.StateIdle, c.State())

	// Reset must also be audited.
	resetRows := repo.Filter(audit.ActionReset)
	require.Len(t, resetRows, 1)
	require.Equal(t, "admin", resetRows[0].Actor)
}

// killHarness wraps the controller plus the audit repo so tests can read
// the rows back without reflection.
type killHarness struct {
	*runtime.Controller
	AuditRepo *audit.MemoryRepo
}

func newKillSetup(t *testing.T) (*killHarness, chan domain.Bar, *paper.Engine) {
	t.Helper()
	eng := paper.NewEngine(decimal.NewFromInt(100_000))
	strat := newMACrossEngine(t)
	rsk := risk.NewEngine(risk.Policy{
		MaxPositionPct:      decimal.NewFromFloat(0.5),
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.5),
		MaxSlippageBps:      30,
		RequireStopLoss:     true,
	})
	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)
	sizer := runtime.FixedFractionSizer(runtime.PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.05),
	})
	pipe := runtime.NewPipeline(strat, rsk, mgr, eng, eng, eng, sizer)
	bars := make(chan domain.Bar, 32)

	repo := audit.NewMemoryRepo()
	rec := audit.NewService(repo)

	c := runtime.NewController(pipe, bars, domain.ModePaper, domain.Symbol("BTCUSDT")).
		WithFlattener(eng).
		WithAuditor(rec)

	return &killHarness{Controller: c, AuditRepo: repo}, bars, eng
}
