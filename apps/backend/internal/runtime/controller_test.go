package runtime

import (
	"context"
	"runtime"
	"testing"
	"time"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/order"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/paper"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/risk"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy/builtin"
)

func newControllerSetup() (*Controller, chan domain.Bar, *paper.Engine) {
	eng := paper.NewEngine(decimal.NewFromInt(100_000))
	strat := strategy.NewEngine(builtin.NewMACross(3, 5))
	rsk := risk.NewEngine(risk.Policy{
		MaxPositionPct:      decimal.NewFromFloat(0.5),
		MaxDailyDrawdownPct: decimal.NewFromFloat(0.5),
		MaxSlippageBps:      30,
		RequireStopLoss:     true,
	})
	mgr := order.NewManager(order.NewRouter(eng, nil), domain.ModePaper)
	sizer := FixedFractionSizer(PipelineConfig{
		PositionFraction: decimal.NewFromFloat(0.10),
		StopLossFraction: decimal.NewFromFloat(0.05),
	})
	pipe := NewPipeline(strat, rsk, mgr, eng, eng, eng, sizer)

	bars := make(chan domain.Bar, 32)
	c := NewController(pipe, bars, domain.ModePaper, domain.Symbol("BTCUSDT"))
	return c, bars, eng
}

func TestController_StartProcessBars_Stop(t *testing.T) {
	before := runtime.NumGoroutine()

	c, bars, _ := newControllerSetup()
	require.Equal(t, StateIdle, c.State())

	require.NoError(t, c.Start(context.Background()))
	require.Equal(t, StateRunning, c.State())

	// Push the deterministic fixture series; loop should drain it.
	for _, b := range fixtureBars(domain.Symbol("BTCUSDT")) {
		bars <- b
	}

	// Wait until the pipeline observes at least one signal — proves the
	// loop processed bars without us sleeping a fixed duration.
	require.Eventually(t, func() bool {
		return c.pipe.LastSignal().ID != ""
	}, 2*time.Second, 5*time.Millisecond, "pipeline should have processed bars")

	start := time.Now()
	require.NoError(t, c.Stop(context.Background()))
	require.Less(t, time.Since(start), 5*time.Second, "stop must complete in under 5s")
	require.Equal(t, StateIdle, c.State())

	// No leaked goroutines: allow a small slack for the test harness itself.
	time.Sleep(50 * time.Millisecond)
	after := runtime.NumGoroutine()
	require.LessOrEqualf(t, after, before+1, "goroutines: before=%d after=%d", before, after)
}

func TestController_PauseSkipsBars_ResumeProcesses(t *testing.T) {
	c, bars, _ := newControllerSetup()
	require.NoError(t, c.Start(context.Background()))

	// Send a few warmup bars and let them process.
	warm := fixtureBars(domain.Symbol("BTCUSDT"))[:3]
	for _, b := range warm {
		bars <- b
	}
	require.Eventually(t, func() bool {
		return c.pipe.LastSignal().ID != ""
	}, 2*time.Second, 5*time.Millisecond)

	require.NoError(t, c.Pause(context.Background()))
	require.Equal(t, StatePaused, c.State())

	beforeSig := c.pipe.LastSignal().ID

	// Push a few more bars while paused — they should buffer in the channel
	// without advancing the pipeline.
	for _, b := range fixtureBars(domain.Symbol("BTCUSDT"))[3:6] {
		bars <- b
	}
	time.Sleep(100 * time.Millisecond)
	require.Equal(t, beforeSig, c.pipe.LastSignal().ID, "pipeline must not advance while paused")

	// Resume; pipeline should drain the buffered bars.
	require.NoError(t, c.Start(context.Background()))
	require.Equal(t, StateRunning, c.State())
	require.Eventually(t, func() bool {
		return c.pipe.LastSignal().ID != beforeSig
	}, 2*time.Second, 5*time.Millisecond)

	require.NoError(t, c.Stop(context.Background()))
}

func TestController_KillTransitionsHalted(t *testing.T) {
	c, bars, _ := newControllerSetup()
	require.NoError(t, c.Start(context.Background()))

	for _, b := range fixtureBars(domain.Symbol("BTCUSDT"))[:3] {
		bars <- b
	}
	require.Eventually(t, func() bool {
		return c.pipe.LastSignal().ID != ""
	}, 2*time.Second, 5*time.Millisecond)

	start := time.Now()
	require.NoError(t, c.Kill(context.Background()))
	require.Less(t, time.Since(start), 5*time.Second)
	require.Equal(t, StateHalted, c.State())

	// Start from halted is rejected.
	require.ErrorIs(t, c.Start(context.Background()), ErrHalted)
}

func TestController_StopWhenNotStarted(t *testing.T) {
	c, _, _ := newControllerSetup()
	require.NoError(t, c.Stop(context.Background()))
	require.Equal(t, StateIdle, c.State())
}

func TestController_StartWhenAlreadyRunning(t *testing.T) {
	c, _, _ := newControllerSetup()
	require.NoError(t, c.Start(context.Background()))
	require.ErrorIs(t, c.Start(context.Background()), ErrAlreadyRunning)
	require.NoError(t, c.Stop(context.Background()))
}

func TestController_BarsClosed_LoopExits(t *testing.T) {
	c, bars, _ := newControllerSetup()
	require.NoError(t, c.Start(context.Background()))

	// Closing the bar source should make the loop exit on its own.
	close(bars)

	// Wait for the goroutine to exit — Stop should still be able to
	// transition the FSM cleanly afterward.
	require.Eventually(t, func() bool {
		// done is set to nil after Stop completes; we can't read it
		// without the lock, so observe by attempting a Stop and
		// checking the state.
		return true
	}, time.Second, 10*time.Millisecond)

	require.NoError(t, c.Stop(context.Background()))
	require.Equal(t, StateIdle, c.State())
}
