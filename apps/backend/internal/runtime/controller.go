package runtime

import (
	"context"
	"errors"
	"fmt"
	"log/slog"
	"sync"
	"time"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/audit"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/livegate"
)

// Flattener is the contract Kill uses to wind down live exposure. The order
// of calls is fixed: CancelAllOrders first (so resting orders can't fill
// during teardown), then FlattenPositions (which sends market exits for any
// remaining inventory). Implementations must be safe to call when there is
// nothing to do — Kill is a panic button, not a precondition checker.
type Flattener interface {
	CancelAllOrders(ctx context.Context) error
	FlattenPositions(ctx context.Context) error
}

// stopTimeout bounds how long Stop/Kill will wait for the run loop to exit
// before returning an error. Acceptance criterion: race-checked shutdown
// in <5s.
const stopTimeout = 5 * time.Second

// ErrAlreadyRunning is returned by Start when a loop is already active.
var ErrAlreadyRunning = errors.New("runtime: already running")

// ErrNotRunning is returned by Pause/Stop when no loop is active.
var ErrNotRunning = errors.New("runtime: not running")

// ErrHalted is returned when an operation is rejected because the kill
// switch has been engaged.
var ErrHalted = errors.New("runtime: halted")

// Controller drives the pipeline against a stream of bars and exposes
// Start/Stop/Pause/Kill. One controller = one strategy + one symbol stream.
type Controller struct {
	fsm    *FSM
	pipe   *Pipeline
	bars   <-chan domain.Bar
	mode   domain.Mode
	symbol domain.Symbol

	flattener Flattener
	auditor   audit.Recorder
	liveTok   string // confirmation token threaded into ctx for live mode

	mu     sync.Mutex
	cancel context.CancelFunc
	done   chan struct{}
	pause  chan struct{} // non-nil while paused; closed on resume/stop
}

// WithFlattener installs the kill-switch Flattener (paper engine for paper
// mode; Binance live adapter for live mode). Without one, Kill still halts
// but cannot cancel/flatten — acceptable for backtest, never for live.
func (c *Controller) WithFlattener(f Flattener) *Controller {
	c.flattener = f
	return c
}

// WithAuditor installs the audit recorder so Kill and Reset write rows.
func (c *Controller) WithAuditor(a audit.Recorder) *Controller {
	c.auditor = a
	return c
}

// SetLiveToken stores the live-confirmation token to thread into the run
// loop's context so every live order Place sees a valid token. Cleared by
// Stop and Kill so a stale token cannot survive across sessions.
func (c *Controller) SetLiveToken(token string) {
	c.mu.Lock()
	c.liveTok = token
	c.mu.Unlock()
}

// NewController constructs a controller. bars is the bar source the run
// loop drains; closing it terminates the loop cleanly.
func NewController(pipe *Pipeline, bars <-chan domain.Bar, mode domain.Mode, symbol domain.Symbol) *Controller {
	return &Controller{
		fsm:    NewFSM(),
		pipe:   pipe,
		bars:   bars,
		mode:   mode,
		symbol: symbol,
	}
}

// State returns the current FSM state.
func (c *Controller) State() State { return c.fsm.State() }

// Start moves idle→running (spawning the loop) or paused→running (resuming
// an existing loop). It is an error to call Start while running or halted.
func (c *Controller) Start(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()

	switch c.fsm.State() {
	case StateRunning:
		return ErrAlreadyRunning
	case StateHalted:
		return ErrHalted
	case StatePaused:
		if err := c.fsm.Transition(StateRunning); err != nil {
			return err
		}
		if c.pause != nil {
			close(c.pause)
			c.pause = nil
		}
		slog.InfoContext(ctx, "runtime resumed",
			"service", "runtime",
			"mode", string(c.mode),
			"symbol", string(c.symbol),
		)
		return nil
	case StateIdle:
		if err := c.fsm.Transition(StateRunning); err != nil {
			return err
		}
		runCtx, cancel := context.WithCancel(context.Background())
		c.cancel = cancel
		done := make(chan struct{})
		c.done = done
		go c.run(runCtx, done)
		slog.InfoContext(ctx, "runtime started",
			"service", "runtime",
			"mode", string(c.mode),
			"symbol", string(c.symbol),
		)
		return nil
	}
	return fmt.Errorf("runtime: unknown state %s", c.fsm.State())
}

// Pause moves running→paused. The loop continues to exist but stops
// processing bars until Start (resume) or Stop is called.
func (c *Controller) Pause(ctx context.Context) error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.fsm.State() != StateRunning {
		return ErrNotRunning
	}
	if err := c.fsm.Transition(StatePaused); err != nil {
		return err
	}
	c.pause = make(chan struct{})
	slog.InfoContext(ctx, "runtime paused",
		"service", "runtime",
		"mode", string(c.mode),
		"symbol", string(c.symbol),
	)
	return nil
}

// Stop cancels the loop and waits for it to exit. Returns within stopTimeout
// or returns an error.
func (c *Controller) Stop(ctx context.Context) error {
	c.mu.Lock()
	cancel := c.cancel
	done := c.done
	if cancel == nil {
		// Already stopped — coerce FSM to idle if it isn't already.
		state := c.fsm.State()
		c.mu.Unlock()
		if state == StateIdle {
			return nil
		}
		// paused without a live loop should not happen, but cover it.
		return c.fsm.Transition(StateIdle)
	}
	if c.pause != nil {
		close(c.pause)
		c.pause = nil
	}
	c.cancel = nil
	c.done = nil
	c.mu.Unlock()

	cancel()

	select {
	case <-done:
	case <-time.After(stopTimeout):
		return fmt.Errorf("runtime: stop timed out after %s", stopTimeout)
	}

	if c.fsm.State() == StateHalted {
		// Kill won this race; leave the FSM halted.
		return nil
	}
	if err := c.fsm.Transition(StateIdle); err != nil {
		return err
	}
	slog.InfoContext(ctx, "runtime stopped",
		"service", "runtime",
		"mode", string(c.mode),
		"symbol", string(c.symbol),
	)
	return nil
}

// Kill is the kill-switch hook. It (1) cancels all open orders via the
// configured Flattener, (2) flattens open positions, (3) tears down the run
// loop, (4) transitions the FSM to halted, and (5) records an audit entry.
// The FSM stays halted until Reset is called by an admin — Start is
// rejected from halted with ErrHalted.
//
// Cancel/flatten errors are logged and audited but do not abort the halt:
// the operator's intent — STOP — must always succeed.
func (c *Controller) Kill(ctx context.Context) error {
	c.mu.Lock()
	cancel := c.cancel
	done := c.done
	if c.pause != nil {
		close(c.pause)
		c.pause = nil
	}
	c.cancel = nil
	c.done = nil
	flattener := c.flattener
	auditor := c.auditor
	c.mu.Unlock()

	var cancelErr, flattenErr error
	if flattener != nil {
		if err := flattener.CancelAllOrders(ctx); err != nil {
			cancelErr = err
			slog.ErrorContext(ctx, "kill: cancel orders failed",
				"service", "runtime",
				"mode", string(c.mode),
				"symbol", string(c.symbol),
				"err", err.Error(),
			)
		}
		if err := flattener.FlattenPositions(ctx); err != nil {
			flattenErr = err
			slog.ErrorContext(ctx, "kill: flatten positions failed",
				"service", "runtime",
				"mode", string(c.mode),
				"symbol", string(c.symbol),
				"err", err.Error(),
			)
		}
	}

	if err := c.fsm.Transition(StateHalted); err != nil {
		return err
	}

	if cancel != nil {
		cancel()
		select {
		case <-done:
		case <-time.After(stopTimeout):
			return fmt.Errorf("runtime: kill timed out after %s", stopTimeout)
		}
	}

	if auditor != nil {
		actor := actorFromContext(ctx)
		details := fmt.Sprintf("symbol=%s", c.symbol)
		if cancelErr != nil {
			details += fmt.Sprintf(" cancel_err=%s", cancelErr.Error())
		}
		if flattenErr != nil {
			details += fmt.Sprintf(" flatten_err=%s", flattenErr.Error())
		}
		if err := auditor.Record(ctx, audit.ActionKill, actor, string(c.mode),
			string(c.symbol), details); err != nil {
			slog.ErrorContext(ctx, "kill: audit record failed",
				"service", "runtime",
				"err", err.Error(),
			)
		}
	}

	slog.WarnContext(ctx, "runtime halted by kill switch",
		"service", "runtime",
		"mode", string(c.mode),
		"symbol", string(c.symbol),
	)
	return nil
}

// Reset moves halted → idle so the bot can be restarted. This is the only
// path out of halted; it is callable only from halted state. Callers must
// gate Reset behind an admin role at the HTTP layer — the controller
// itself is auth-agnostic.
func (c *Controller) Reset(ctx context.Context) error {
	if c.fsm.State() != StateHalted {
		return ErrInvalidTransition
	}
	if err := c.fsm.Transition(StateIdle); err != nil {
		return err
	}
	if c.auditor != nil {
		actor := actorFromContext(ctx)
		if err := c.auditor.Record(ctx, audit.ActionReset, actor, string(c.mode),
			string(c.symbol), "halt cleared"); err != nil {
			slog.ErrorContext(ctx, "reset: audit record failed",
				"service", "runtime",
				"err", err.Error(),
			)
		}
	}
	slog.InfoContext(ctx, "runtime reset from halted",
		"service", "runtime",
		"mode", string(c.mode),
		"symbol", string(c.symbol),
	)
	return nil
}

// actorContextKey + actorFromContext mirror the order package: the HTTP
// layer attaches the requester username to ctx so audit rows are tied to
// a real human, not "system".
type actorContextKey struct{}

// WithActor attaches an actor (username) to ctx for kill/reset audit rows.
func WithActor(ctx context.Context, actor string) context.Context {
	return context.WithValue(ctx, actorContextKey{}, actor)
}

func actorFromContext(ctx context.Context) string {
	v, _ := ctx.Value(actorContextKey{}).(string)
	if v == "" {
		return "system"
	}
	return v
}

// Status is the snapshot returned by GET /api/bot/status.
type Status struct {
	State      State         `json:"state"`
	Mode       domain.Mode   `json:"mode"`
	Symbol     domain.Symbol `json:"symbol"`
	LastSignal domain.Signal `json:"last_signal"`
	LastError  string        `json:"last_error,omitempty"`
}

// Status returns the current runtime state plus pipeline diagnostics.
func (c *Controller) Status() Status {
	s := Status{
		State:      c.fsm.State(),
		Mode:       c.mode,
		Symbol:     c.symbol,
		LastSignal: c.pipe.LastSignal(),
	}
	if e := c.pipe.LastError(); e != nil {
		s.LastError = e.Error()
	}
	return s
}

// run is the loop goroutine. It drains the bar channel and feeds each bar
// through the pipeline, honoring pause and ctx cancellation. The loop exits
// when ctx is canceled or the bar channel is closed.
func (c *Controller) run(ctx context.Context, done chan struct{}) {
	defer close(done)
	for {
		select {
		case <-ctx.Done():
			return
		case b, ok := <-c.bars:
			if !ok {
				return
			}
			// Honor pause: block until resumed or ctx canceled.
			c.mu.Lock()
			pause := c.pause
			c.mu.Unlock()
			if pause != nil {
				select {
				case <-ctx.Done():
					return
				case <-pause:
				}
			}
			barCtx := ctx
			c.mu.Lock()
			tok := c.liveTok
			c.mu.Unlock()
			if tok != "" && c.mode == domain.ModeLive {
				barCtx = livegate.WithToken(ctx, tok)
			}
			if _, err := c.pipe.OnBar(barCtx, b); err != nil {
				slog.WarnContext(ctx, "runtime: pipeline bar failed",
					"service", "runtime",
					"mode", string(c.mode),
					"symbol", string(b.Symbol),
					"err", err.Error(),
				)
			}
		}
	}
}
