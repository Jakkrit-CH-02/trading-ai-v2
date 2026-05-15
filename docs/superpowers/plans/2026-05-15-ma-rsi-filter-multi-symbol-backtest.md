# MA+RSI Filter Strategy + Multi-Symbol Backtest — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `ma_rsi_filter` composite strategy (EMA cross gated by RSI) and multi-symbol backtest support (up to 10 symbols per run, comparison table in UI).

**Architecture:** The strategy is a pure Go struct composing the existing `MACross` and `RSI` types; a new `CurrentRSI()` method is added to `RSI` to expose its computed value. The multi-symbol endpoint loops over symbols sequentially, reusing the existing single-run engine. The frontend switches the Symbol text input to a multi-select chip input and dispatches to the new `/api/backtest/multi` endpoint when more than one symbol is selected.

**Tech Stack:** Go 1.22, github.com/shopspring/decimal, gofiber/fiber v2, React 18 + MUI v5, react-hook-form, TanStack Query, zod, vitest + testing-library

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `apps/backend/internal/strategy/builtin/rsi.go` | Modify | Add `CurrentRSI() (decimal.Decimal, bool)` |
| `apps/backend/internal/strategy/builtin/ma_rsi_filter.go` | Create | `MARSIFilter` struct, `MARSIFilterFactory` |
| `apps/backend/internal/strategy/builtin/ma_rsi_filter_test.go` | Create | Unit tests for composite strategy |
| `apps/backend/internal/api/server.go` | Modify | Register `"ma_rsi_filter"` in strategy registry |
| `apps/backend/internal/backtest/handler.go` | Modify | Add `validateMultiSymbols`, `runMulti` handler |
| `apps/backend/internal/backtest/router.go` | Modify | Register `POST /api/backtest/multi` |
| `apps/frontend/src/api/backtest.ts` | Modify | Add `RunMultiBacktestInput`, `MultiBacktestResult`, `runMultiBacktest` |
| `apps/frontend/src/pages/backtest/BacktestRunForm.tsx` | Modify | Symbol multi-select, RSI fields, timeframe presets |
| `apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx` | Create | KPI comparison table across symbols |
| `apps/frontend/src/pages/backtest/BacktestPage.tsx` | Modify | Multi-symbol routing, accordion results |

---

## Task 1: Expose RSI value + implement `ma_rsi_filter` strategy

**Files:**
- Modify: `apps/backend/internal/strategy/builtin/rsi.go`
- Create: `apps/backend/internal/strategy/builtin/ma_rsi_filter.go`
- Create: `apps/backend/internal/strategy/builtin/ma_rsi_filter_test.go`

- [ ] **Step 1: Write failing tests**

Create `apps/backend/internal/strategy/builtin/ma_rsi_filter_test.go`:

```go
package builtin

import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
)

func TestMARSIFilter_Warmup(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	ctx := context.Background()
	for i := 0; i < 25; i++ {
		sig, err := f.OnBar(ctx, mkBar(100))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action,
			"bar %d should be Hold during warmup", i)
	}
}

// TestMARSIFilter_BuyBlocked_HighRSI: flat prices make avgLoss=0 → RSI=100.
// A cross-up fires but RSI (100) ≥ rsi_buy_max (60) → gate blocks.
func TestMARSIFilter_BuyBlocked_HighRSI(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	ctx := context.Background()

	for i := 0; i < 22; i++ {
		sig, err := f.OnBar(ctx, mkBar(100))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action)
	}

	// Bar 23 at 101: EMA9 crosses above EMA21, but RSI = 100 ≥ 60 → blocked
	sig, err := f.OnBar(ctx, mkBar(101))
	require.NoError(t, err)
	require.Equal(t, domain.SignalActionHold, sig.Action, "high RSI should block buy")
	require.Contains(t, sig.Reason, "rsi_gate_blocked")
}

// TestMARSIFilter_BuyAllowed: alternating 99/101 keeps RSI ≈ 50.
// Jump to 105 triggers EMA cross-up with RSI ≈ 59 < 60 → Buy emitted.
func TestMARSIFilter_BuyAllowed(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	ctx := context.Background()

	for i := 0; i < 35; i++ {
		price := 101.0
		if i%2 == 0 {
			price = 99.0
		}
		sig, err := f.OnBar(ctx, mkBar(price))
		require.NoError(t, err)
		require.Equal(t, domain.SignalActionHold, sig.Action, "bar %d should be Hold", i)
	}

	// Jump to 105: EMA9 crosses EMA21, RSI ≈ 59 < 60 → Buy allowed
	sig, err := f.OnBar(ctx, mkBar(105))
	require.NoError(t, err)
	require.Equal(t, domain.SignalActionBuy, sig.Action)
	require.Contains(t, sig.Reason, "rsi")
}

func TestMARSIFilter_Name(t *testing.T) {
	f := NewMARSIFilter(9, 21, 14, decimal.NewFromInt(60), decimal.NewFromInt(40))
	require.Equal(t, "ma_rsi_filter", f.Name())
}

func TestMARSIFilterFactory_Defaults(t *testing.T) {
	strat, err := MARSIFilterFactory(strategy.RuleConfig{
		Name:    "ma_rsi_filter",
		Enabled: true,
		Params:  map[string]string{},
	})
	require.NoError(t, err)
	require.Equal(t, "ma_rsi_filter", strat.Name())
}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd apps/backend && go test ./internal/strategy/builtin/ -run TestMARSIFilter -v
```

Expected: compile error — `NewMARSIFilter`, `MARSIFilterFactory` not defined yet.

- [ ] **Step 3: Add `CurrentRSI()` to RSI**

In `apps/backend/internal/strategy/builtin/rsi.go`, add this method after `compute()`:

```go
// CurrentRSI returns the current RSI value and whether the indicator has warmed up.
func (r *RSI) CurrentRSI() (decimal.Decimal, bool) {
	if !r.ready {
		return decimal.Zero, false
	}
	return r.compute(), true
}
```

- [ ] **Step 4: Implement `ma_rsi_filter.go`**

Create `apps/backend/internal/strategy/builtin/ma_rsi_filter.go`:

```go
package builtin

import (
	"context"
	"fmt"

	"github.com/shopspring/decimal"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/timex"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)

const MARSIFilterName = "ma_rsi_filter"

// MARSIFilter emits MA crossover signals only when the RSI gate condition is met:
// BUY cross fires only when RSI < rsiBuyMax; SELL cross fires only when RSI > rsiSellMin.
type MARSIFilter struct {
	ma         *MACross
	rsiCalc    *RSI
	rsiBuyMax  decimal.Decimal
	rsiSellMin decimal.Decimal
}

func NewMARSIFilter(fast, slow, rsiPeriod int, rsiBuyMax, rsiSellMin decimal.Decimal) *MARSIFilter {
	return &MARSIFilter{
		ma:         NewMACross(fast, slow),
		rsiCalc:    NewRSI(rsiPeriod, decimal.NewFromInt(30), decimal.NewFromInt(70)),
		rsiBuyMax:  rsiBuyMax,
		rsiSellMin: rsiSellMin,
	}
}

func (f *MARSIFilter) Name() string { return MARSIFilterName }

func (f *MARSIFilter) OnBar(ctx context.Context, b domain.Bar) (strategy.Signal, error) {
	maSig, err := f.ma.OnBar(ctx, b)
	if err != nil {
		return strategy.Signal{}, err
	}
	if _, err = f.rsiCalc.OnBar(ctx, b); err != nil {
		return strategy.Signal{}, err
	}

	hold := strategy.Signal{
		ID:        ids.New(),
		Symbol:    b.Symbol,
		Action:    domain.SignalActionHold,
		Strategy:  MARSIFilterName,
		CreatedMs: timex.NowMs(),
	}

	if maSig.Action == domain.SignalActionHold {
		hold.Reason = maSig.Reason
		return hold, nil
	}

	rsiVal, rsiReady := f.rsiCalc.CurrentRSI()
	if !rsiReady {
		hold.Reason = "warmup"
		return hold, nil
	}

	switch maSig.Action {
	case domain.SignalActionBuy:
		if rsiVal.LessThan(f.rsiBuyMax) {
			return strategy.Signal{
				ID:        ids.New(),
				Symbol:    b.Symbol,
				Action:    domain.SignalActionBuy,
				Strategy:  MARSIFilterName,
				Reason:    fmt.Sprintf("%s; rsi %.2f < buy_max %.2f", maSig.Reason, rsiVal.InexactFloat64(), f.rsiBuyMax.InexactFloat64()),
				Strength:  maSig.Strength,
				CreatedMs: timex.NowMs(),
			}, nil
		}
		hold.Reason = fmt.Sprintf("rsi_gate_blocked: rsi %.2f >= buy_max %.2f", rsiVal.InexactFloat64(), f.rsiBuyMax.InexactFloat64())
	case domain.SignalActionSell:
		if rsiVal.GreaterThan(f.rsiSellMin) {
			return strategy.Signal{
				ID:        ids.New(),
				Symbol:    b.Symbol,
				Action:    domain.SignalActionSell,
				Strategy:  MARSIFilterName,
				Reason:    fmt.Sprintf("%s; rsi %.2f > sell_min %.2f", maSig.Reason, rsiVal.InexactFloat64(), f.rsiSellMin.InexactFloat64()),
				Strength:  maSig.Strength,
				CreatedMs: timex.NowMs(),
			}, nil
		}
		hold.Reason = fmt.Sprintf("rsi_gate_blocked: rsi %.2f <= sell_min %.2f", rsiVal.InexactFloat64(), f.rsiSellMin.InexactFloat64())
	}

	return hold, nil
}

// MARSIFilterFactory builds MARSIFilter from a RuleConfig.
// Params: "fast" (default 9), "slow" (default 21), "rsi_period" (default 14),
//         "rsi_buy_max" (default 60), "rsi_sell_min" (default 40).
func MARSIFilterFactory(cfg strategy.RuleConfig) (strategy.Strategy, error) {
	fast, err := paramInt(cfg.Params, "fast", 9)
	if err != nil {
		return nil, err
	}
	slow, err := paramInt(cfg.Params, "slow", 21)
	if err != nil {
		return nil, err
	}
	rsiPeriod, err := paramInt(cfg.Params, "rsi_period", 14)
	if err != nil {
		return nil, err
	}
	rsiBuyMax, err := paramDecimal(cfg.Params, "rsi_buy_max", decimal.NewFromInt(60))
	if err != nil {
		return nil, err
	}
	rsiSellMin, err := paramDecimal(cfg.Params, "rsi_sell_min", decimal.NewFromInt(40))
	if err != nil {
		return nil, err
	}
	return NewMARSIFilter(fast, slow, rsiPeriod, rsiBuyMax, rsiSellMin), nil
}
```

- [ ] **Step 5: Add missing import to the test file**

At the top of `ma_rsi_filter_test.go`, add the missing import (needed for `MARSIFilterFactory`):

```go
import (
	"context"
	"testing"

	"github.com/shopspring/decimal"
	"github.com/stretchr/testify/require"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/domain"
	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/strategy"
)
```

- [ ] **Step 6: Run tests — expect pass**

```bash
cd apps/backend && go test ./internal/strategy/builtin/ -run TestMARSIFilter -v
```

Expected output: all 4 tests PASS.

- [ ] **Step 7: Run full strategy package tests to check for regressions**

```bash
cd apps/backend && go test ./internal/strategy/... -v
```

Expected: all existing tests plus new ones PASS.

- [ ] **Step 8: Commit**

```bash
git add apps/backend/internal/strategy/builtin/rsi.go \
        apps/backend/internal/strategy/builtin/ma_rsi_filter.go \
        apps/backend/internal/strategy/builtin/ma_rsi_filter_test.go
git commit -m "feat(strategy): add ma_rsi_filter composite strategy"
```

---

## Task 2: Register `ma_rsi_filter` in the strategy registry

**Files:**
- Modify: `apps/backend/internal/api/server.go`

- [ ] **Step 1: Add registration line**

In `apps/backend/internal/api/server.go`, find the block that registers strategies (currently lines ~219–229). Add one line after the RSI registration:

```go
registry.Register(builtin.MACrossName, builtin.MACrossFactory)
registry.Register(builtin.RSIName, builtin.RSIFactory)
registry.Register(builtin.MARSIFilterName, builtin.MARSIFilterFactory)  // ← add this
registry.Register(builtin.AIName, func(cfg strategy.RuleConfig) (strategy.Strategy, error) {
```

- [ ] **Step 2: Build to verify no compile errors**

```bash
cd apps/backend && go build ./...
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/backend/internal/api/server.go
git commit -m "feat(strategy): register ma_rsi_filter in strategy registry"
```

---

## Task 3: Multi-symbol backtest endpoint

**Files:**
- Modify: `apps/backend/internal/backtest/handler.go`
- Modify: `apps/backend/internal/backtest/router.go`

- [ ] **Step 1: Write failing test for symbol validation**

In `apps/backend/internal/backtest/handler_test.go`, add at the bottom:

```go
func TestValidateMultiSymbols(t *testing.T) {
	cases := []struct {
		name    string
		symbols []string
		wantErr string
	}{
		{"empty", []string{}, "symbols is required"},
		{"too many", make([]string, 11), "at most 10"},
		{"one symbol", []string{"BTCUSDT"}, ""},
		{"ten symbols", make([]string, 10), ""},
	}
	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			err := validateMultiSymbols(tc.symbols)
			if tc.wantErr != "" {
				require.ErrorContains(t, err, tc.wantErr)
			} else {
				require.NoError(t, err)
			}
		})
	}
}
```

- [ ] **Step 2: Run test to confirm it fails**

```bash
cd apps/backend && go test ./internal/backtest/ -run TestValidateMultiSymbols -v
```

Expected: compile error — `validateMultiSymbols` not defined yet.

- [ ] **Step 3: Implement `validateMultiSymbols` and `runMulti` handler**

In `apps/backend/internal/backtest/handler.go`, add after the `list` handler:

```go
func validateMultiSymbols(symbols []string) error {
	if len(symbols) == 0 {
		return fmt.Errorf("symbols is required")
	}
	if len(symbols) > 10 {
		return fmt.Errorf("symbols must have at most 10 entries")
	}
	return nil
}

// MultiRunRequest is the wire DTO for POST /api/backtest/multi.
type MultiRunRequest struct {
	Symbols            []string          `json:"symbols"`
	Interval           string            `json:"interval"`
	StrategyName       string            `json:"strategy_name"`
	StrategyParams     map[string]string `json:"strategy_params"`
	InitialCash        string            `json:"initial_cash"`
	PositionFraction   string            `json:"position_fraction"`
	StopLossPct        string            `json:"stop_loss_pct"`
	TrailActivationPct string            `json:"trail_activation_pct"`
	TrailPct           string            `json:"trail_pct"`
	FromMs             int64             `json:"from_ms"`
	ToMs               int64             `json:"to_ms"`
	Limit              int               `json:"limit"`
}

func (h *Handler) runMulti(c *fiber.Ctx) error {
	var req MultiRunRequest
	if err := c.BodyParser(&req); err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", "invalid json body")
	}
	if err := validateMultiSymbols(req.Symbols); err != nil {
		return errResp(c, fiber.StatusBadRequest, "validation_failed", err.Error())
	}
	if h.bars == nil {
		return errResp(c, fiber.StatusServiceUnavailable, "internal", "bar source not configured")
	}
	if h.registry == nil {
		return errResp(c, fiber.StatusServiceUnavailable, "internal", "strategy registry not configured")
	}

	results := make([]Result, 0, len(req.Symbols))
	for _, sym := range req.Symbols {
		single := RunRequest{
			Symbol:             strings.ToUpper(strings.TrimSpace(sym)),
			Interval:           req.Interval,
			StrategyName:       req.StrategyName,
			StrategyParams:     req.StrategyParams,
			InitialCash:        req.InitialCash,
			PositionFraction:   req.PositionFraction,
			StopLossPct:        req.StopLossPct,
			TrailActivationPct: req.TrailActivationPct,
			TrailPct:           req.TrailPct,
			FromMs:             req.FromMs,
			ToMs:               req.ToMs,
			Limit:              req.Limit,
		}
		cfg, err := single.toConfig()
		if err != nil {
			return errResp(c, fiber.StatusBadRequest, "validation_failed",
				fmt.Sprintf("%s: %s", sym, err.Error()))
		}
		strat, err := h.registry.Build(strategy.RuleConfig{
			Name:    cfg.StrategyName,
			Enabled: true,
			Symbol:  string(cfg.Symbol),
			Params:  cfg.StrategyParams,
		})
		if err != nil {
			return errResp(c, fiber.StatusBadRequest, "validation_failed", err.Error())
		}
		limit := resolveBacktestLimit(cfg, req.Limit)
		bars, err := h.loadBars(c.UserContext(), cfg, limit)
		if err != nil {
			return errResp(c, fiber.StatusInternalServerError, "internal", err.Error())
		}
		if len(bars) == 0 {
			return errResp(c, fiber.StatusNotFound, "not_found",
				fmt.Sprintf("no bars available for %s/%s", sym, req.Interval))
		}
		backtestRisk := risk.NewEngine(risk.Policy{
			MaxPositionPct:      cfg.PositionFraction,
			MaxDailyDrawdownPct: decimal.NewFromFloat(1),
			MaxSlippageBps:      1_000_000,
			RequireStopLoss:     true,
		})
		res, err := NewEngine(cfg, strat, backtestRisk).Run(c.UserContext(), bars)
		if err != nil {
			return errResp(c, fiber.StatusBadRequest, "validation_failed", err.Error())
		}
		results = append(results, res)
	}

	return c.JSON(okEnv(struct {
		Results []Result `json:"results"`
	}{Results: results}))
}
```

- [ ] **Step 4: Register the route**

In `apps/backend/internal/backtest/router.go`, add one line:

```go
func RegisterRoutes(app *fiber.App, h *Handler) {
	app.Post("/api/backtest/run", h.run)
	app.Post("/api/backtest/multi", h.runMulti)  // ← add this
	app.Get("/api/backtest", h.list)
	app.Get("/api/backtest/:id", h.get)
}
```

- [ ] **Step 5: Run tests — expect pass**

```bash
cd apps/backend && go test ./internal/backtest/ -run TestValidateMultiSymbols -v
```

Expected: PASS.

- [ ] **Step 6: Build to check for compile errors**

```bash
cd apps/backend && go build ./...
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add apps/backend/internal/backtest/handler.go \
        apps/backend/internal/backtest/handler_test.go \
        apps/backend/internal/backtest/router.go
git commit -m "feat(backtest): add multi-symbol backtest endpoint POST /api/backtest/multi"
```

---

## Task 4: Frontend API layer — multi-symbol types and function

**Files:**
- Modify: `apps/frontend/src/api/backtest.ts`

- [ ] **Step 1: Add types and `runMultiBacktest` function**

In `apps/frontend/src/api/backtest.ts`, add after the `runBacktest` function:

```typescript
export interface RunMultiBacktestInput {
  symbols: string[];
  interval: string;
  strategy_name: string;
  strategy_params?: Record<string, string>;
  initial_cash?: string;
  position_fraction?: string;
  stop_loss_pct?: string;
  trail_activation_pct?: string;
  trail_pct?: string;
  from_ms?: number;
  to_ms?: number;
  limit?: number;
}

export const MultiBacktestResultSchema = z.object({
  results: z.array(BacktestResultSchema),
});
export type MultiBacktestResult = z.infer<typeof MultiBacktestResultSchema>;

export async function runMultiBacktest(
  input: RunMultiBacktestInput,
): Promise<MultiBacktestResult> {
  const { data } = await api.post<ApiEnvelope<unknown>>(
    "/api/backtest/multi",
    input,
  );
  return unwrap(data, MultiBacktestResultSchema);
}
```

- [ ] **Step 2: Typecheck**

```bash
cd apps/frontend && pnpm typecheck 2>&1 | head -30
```

Expected: no errors in `src/api/backtest.ts`.

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/src/api/backtest.ts
git commit -m "feat(backtest): add RunMultiBacktestInput type and runMultiBacktest API function"
```

---

## Task 5: BacktestRunForm — symbol multi-select, RSI fields, timeframe presets

**Files:**
- Modify: `apps/frontend/src/pages/backtest/BacktestRunForm.tsx`

- [ ] **Step 1: Replace the entire file with the updated version**

Replace `apps/frontend/src/pages/backtest/BacktestRunForm.tsx` with:

```typescript
import {
  Autocomplete,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  FormHelperText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import PlayArrowIcon from "@mui/icons-material/PlayArrow";
import { useEffect } from "react";
import { Controller, useForm } from "react-hook-form";
import type { RunMultiBacktestInput } from "../../api/backtest";

const STRATEGIES = [
  { value: "ma_cross", label: "MA Crossover" },
  { value: "ma_rsi_filter", label: "MA + RSI Filter" },
  { value: "rsi", label: "RSI" },
  { value: "ai", label: "AI Model" },
];

const INTERVALS = ["1m", "5m", "15m", "1h", "4h", "1d"];

const SYMBOL_PRESETS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "XRPUSDT"];

const TIMEFRAME_PRESETS: Record<
  string,
  { fast: number; slow: number; rsiPeriod: number }
> = {
  "1m":  { fast: 3,  slow: 8,  rsiPeriod: 7  },
  "5m":  { fast: 5,  slow: 13, rsiPeriod: 10 },
  "15m": { fast: 8,  slow: 21, rsiPeriod: 14 },
  "1h":  { fast: 9,  slow: 21, rsiPeriod: 14 },
  "4h":  { fast: 9,  slow: 21, rsiPeriod: 14 },
  "1d":  { fast: 12, slow: 26, rsiPeriod: 14 },
};

export interface BacktestRunFormValues {
  symbols: string[];
  interval: string;
  strategy_name: string;
  initial_cash: string;
  position_fraction: string;
  stop_loss_pct: string;
  trail_activation_pct: string;
  trail_pct: string;
  from: string;
  to: string;
  limit: string;
  fast_period: string;
  slow_period: string;
  rsi_period: string;
  rsi_buy_max: string;
  rsi_sell_min: string;
}

export interface BacktestRunFormProps {
  onSubmit: (input: RunMultiBacktestInput) => void;
  pending: boolean;
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", sm: "1fr 1fr", md: "repeat(3, 1fr)" },
  },
} as const;

export default function BacktestRunForm(props: BacktestRunFormProps) {
  const { onSubmit, pending } = props;
  const { register, handleSubmit, watch, control, setValue } =
    useForm<BacktestRunFormValues>({
      defaultValues: {
        symbols: ["BTCUSDT"],
        interval: "4h",
        strategy_name: "ma_rsi_filter",
        initial_cash: "10000",
        position_fraction: "0.1",
        stop_loss_pct: "0.08",
        trail_activation_pct: "0.03",
        trail_pct: "0.02",
        from: "",
        to: "",
        limit: "",
        fast_period: "9",
        slow_period: "21",
        rsi_period: "14",
        rsi_buy_max: "60",
        rsi_sell_min: "40",
      },
    });

  const strategy_name = watch("strategy_name");
  const interval = watch("interval");
  const from = watch("from");
  const to = watch("to");

  // Auto-populate EMA/RSI period fields when strategy + interval change.
  useEffect(() => {
    if (strategy_name !== "ma_rsi_filter") return;
    const preset = TIMEFRAME_PRESETS[interval];
    if (!preset) return;
    setValue("fast_period", String(preset.fast));
    setValue("slow_period", String(preset.slow));
    setValue("rsi_period", String(preset.rsiPeriod));
  }, [interval, strategy_name, setValue]);

  const isMACross = strategy_name === "ma_cross";
  const isMARSI = strategy_name === "ma_rsi_filter";

  const submit = handleSubmit((v) => {
    const fromMs = v.from ? Date.parse(v.from) : 0;
    const toMs = v.to ? Date.parse(v.to) : Date.now();
    const params: Record<string, string> = {};
    if (isMACross) {
      if (v.fast_period) params.fast = v.fast_period;
      if (v.slow_period) params.slow = v.slow_period;
    }
    if (isMARSI) {
      if (v.fast_period) params.fast = v.fast_period;
      if (v.slow_period) params.slow = v.slow_period;
      if (v.rsi_period) params.rsi_period = v.rsi_period;
      if (v.rsi_buy_max) params.rsi_buy_max = v.rsi_buy_max;
      if (v.rsi_sell_min) params.rsi_sell_min = v.rsi_sell_min;
    }
    const derivedLimit = estimateLimit(v.interval, fromMs, toMs);
    const input: RunMultiBacktestInput = {
      symbols: v.symbols.map((s) => s.trim().toUpperCase()).filter(Boolean),
      interval: v.interval,
      strategy_name: v.strategy_name,
      strategy_params: params,
      initial_cash: v.initial_cash,
      position_fraction: v.position_fraction,
      stop_loss_pct: v.stop_loss_pct,
      trail_activation_pct: v.trail_activation_pct || undefined,
      trail_pct: v.trail_pct || undefined,
      from_ms: Number.isFinite(fromMs) && fromMs > 0 ? fromMs : undefined,
      to_ms:
        Number.isFinite(toMs) && toMs > 0 && v.from ? toMs : undefined,
      limit: v.limit ? Number(v.limit) : derivedLimit,
    };
    onSubmit(input);
  });

  const estimatedBars = estimateLimit(
    interval,
    from ? Date.parse(from) : 0,
    to ? Date.parse(to) : Date.now(),
  );
  const isLongRange =
    Boolean(from) && estimatedBars !== undefined && estimatedBars > 5000;

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Launch Backtest
        </Typography>
        <Box component="form" onSubmit={submit}>
          <Box sx={styles.grid}>
            <Controller
              name="symbols"
              control={control}
              render={({ field }) => (
                <Autocomplete
                  multiple
                  freeSolo
                  options={SYMBOL_PRESETS}
                  value={field.value}
                  onChange={(_, v) => field.onChange(v)}
                  renderTags={(value, getTagProps) =>
                    value.map((option, index) => (
                      <Chip
                        {...getTagProps({ index })}
                        key={option}
                        label={option}
                        size="small"
                      />
                    ))
                  }
                  renderInput={(params) => (
                    <TextField
                      {...params}
                      label="Symbol(s)"
                      size="small"
                      placeholder={field.value.length === 0 ? "BTCUSDT" : ""}
                    />
                  )}
                />
              )}
            />
            <TextField
              label="Interval"
              size="small"
              select
              {...register("interval")}
            >
              {INTERVALS.map((i) => (
                <MenuItem key={i} value={i}>
                  {i}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Strategy"
              size="small"
              select
              {...register("strategy_name")}
            >
              {STRATEGIES.map((s) => (
                <MenuItem key={s.value} value={s.value}>
                  {s.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="From (UTC)"
              size="small"
              type="datetime-local"
              InputLabelProps={{ shrink: true }}
              {...register("from")}
            />
            <TextField
              label="To (UTC)"
              size="small"
              type="datetime-local"
              InputLabelProps={{ shrink: true }}
              {...register("to")}
            />
            <TextField
              label="Bar limit"
              size="small"
              type="number"
              {...register("limit")}
            />
            <TextField
              label="Initial cash"
              size="small"
              {...register("initial_cash")}
            />
            <TextField
              label="Position fraction (0..1)"
              size="small"
              {...register("position_fraction")}
            />
            <TextField
              label="Stop loss pct (0..1)"
              size="small"
              {...register("stop_loss_pct")}
            />
            <TextField
              label="Trail Activation % (0..1)"
              size="small"
              {...register("trail_activation_pct")}
            />
            <TextField
              label="Trail Distance % (0..1)"
              size="small"
              {...register("trail_pct")}
            />
            {isMACross || isMARSI ? (
              <>
                <TextField
                  label="Fast period"
                  size="small"
                  type="number"
                  {...register("fast_period")}
                />
                <TextField
                  label="Slow period"
                  size="small"
                  type="number"
                  {...register("slow_period")}
                />
              </>
            ) : null}
            {isMARSI ? (
              <>
                <TextField
                  label="RSI Period"
                  size="small"
                  type="number"
                  {...register("rsi_period")}
                />
                <TextField
                  label="RSI Buy Max (0..100)"
                  size="small"
                  type="number"
                  {...register("rsi_buy_max")}
                />
                <TextField
                  label="RSI Sell Min (0..100)"
                  size="small"
                  type="number"
                  {...register("rsi_sell_min")}
                />
              </>
            ) : null}
          </Box>
          <FormHelperText sx={{ mt: 1 }}>
            Leave `Bar limit` blank to auto-size from the selected range. For
            quick visual verification, use `1h` or `4h` on long ranges; `1m`
            over months can still be slow.
          </FormHelperText>
          {isLongRange ? (
            <FormHelperText sx={{ mt: 0.5 }} error>
              This range is about {estimatedBars?.toLocaleString()} bars at `
              {interval}`. The app will cap the run to 10,000 bars unless you
              narrow the range or increase the interval.
            </FormHelperText>
          ) : null}
          <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
            <Button
              type="submit"
              variant="contained"
              startIcon={
                pending ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  <PlayArrowIcon />
                )
              }
              disabled={pending}
            >
              {pending ? "Running…" : "Run Backtest"}
            </Button>
          </Stack>
        </Box>
      </CardContent>
    </Card>
  );
}

function estimateLimit(
  interval: string,
  fromMs: number,
  toMs: number,
): number | undefined {
  if (
    !Number.isFinite(fromMs) ||
    fromMs <= 0 ||
    !Number.isFinite(toMs) ||
    toMs <= fromMs
  ) {
    return undefined;
  }
  const stepMs = intervalToMs(interval);
  if (!stepMs) return undefined;
  const bars = Math.floor((toMs - fromMs) / stepMs) + 1;
  return Math.min(Math.max(bars, 1), 10000);
}

function intervalToMs(interval: string): number | undefined {
  const value = Number(interval.slice(0, -1));
  if (!Number.isFinite(value) || value <= 0) return undefined;
  const unit = interval.slice(-1);
  switch (unit) {
    case "m": return value * 60_000;
    case "h": return value * 3_600_000;
    case "d": return value * 86_400_000;
    default:  return undefined;
  }
}
```

- [ ] **Step 2: Typecheck**

```bash
cd apps/frontend && pnpm typecheck 2>&1 | head -40
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/src/pages/backtest/BacktestRunForm.tsx
git commit -m "feat(backtest): symbol multi-select, MA+RSI Filter strategy, timeframe presets"
```

---

## Task 6: `BacktestComparisonTable` component

**Files:**
- Create: `apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx`

- [ ] **Step 1: Create the component**

Create `apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx`:

```typescript
import {
  Box,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from "@mui/material";
import { useState } from "react";
import type { BacktestResult } from "../../api/backtest";

export interface BacktestComparisonTableProps {
  results: BacktestResult[];
}

type SortKey = "symbol" | "total_return" | "win_rate" | "sharpe_ratio" | "max_drawdown" | "total_trades";

const styles = {
  positive: { color: "success.main", fontWeight: 600 },
  negative: { color: "error.main", fontWeight: 600 },
  header: { fontWeight: 700, fontSize: 12, letterSpacing: 0.5, color: "text.secondary" },
} as const;

function pct(s: string): string {
  const n = Number(s);
  return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : "—";
}

function num(s: string, digits = 2): string {
  const n = Number(s);
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

export default function BacktestComparisonTable(
  props: BacktestComparisonTableProps,
) {
  const { results } = props;
  const [sortKey, setSortKey] = useState<SortKey>("total_return");
  const [sortAsc, setSortAsc] = useState(false);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc((prev) => !prev);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const sorted = [...results].sort((a, b) => {
    let va: number, vb: number;
    if (sortKey === "symbol") {
      return sortAsc
        ? a.config.symbol.localeCompare(b.config.symbol)
        : b.config.symbol.localeCompare(a.config.symbol);
    }
    if (sortKey === "total_trades") {
      va = a.metrics.total_trades;
      vb = b.metrics.total_trades;
    } else {
      va = Number(a.metrics[sortKey]);
      vb = Number(b.metrics[sortKey]);
    }
    return sortAsc ? va - vb : vb - va;
  });

  const col = (key: SortKey, label: string) => (
    <TableCell sx={styles.header}>
      <TableSortLabel
        active={sortKey === key}
        direction={sortKey === key ? (sortAsc ? "asc" : "desc") : "desc"}
        onClick={() => handleSort(key)}
      >
        {label}
      </TableSortLabel>
    </TableCell>
  );

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Symbol Comparison
        </Typography>
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {col("symbol", "SYMBOL")}
                {col("total_return", "TOTAL RETURN")}
                {col("win_rate", "WIN RATE")}
                {col("sharpe_ratio", "SHARPE")}
                {col("max_drawdown", "MAX DRAWDOWN")}
                {col("total_trades", "TRADES")}
              </TableRow>
            </TableHead>
            <TableBody>
              {sorted.map((r) => {
                const ret = Number(r.metrics.total_return);
                const retColor =
                  ret > 0 ? "success.main" : ret < 0 ? "error.main" : "text.primary";
                return (
                  <TableRow key={r.config.symbol} hover>
                    <TableCell sx={{ fontWeight: 600 }}>
                      {r.config.symbol}
                    </TableCell>
                    <TableCell sx={{ color: retColor, fontWeight: 600 }}>
                      {pct(r.metrics.total_return)}
                    </TableCell>
                    <TableCell>{pct(r.metrics.win_rate)}</TableCell>
                    <TableCell>{num(r.metrics.sharpe_ratio)}</TableCell>
                    <TableCell sx={{ color: "error.main" }}>
                      {pct(r.metrics.max_drawdown)}
                    </TableCell>
                    <TableCell>
                      {r.metrics.total_trades}{" "}
                      <Typography
                        component="span"
                        sx={{ fontSize: 11, color: "text.secondary" }}
                      >
                        ({r.metrics.winning_trades}W/{r.metrics.losing_trades}L)
                      </Typography>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Typecheck**

```bash
cd apps/frontend && pnpm typecheck 2>&1 | head -20
```

Expected: no errors.

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx
git commit -m "feat(backtest): add BacktestComparisonTable for multi-symbol KPI comparison"
```

---

## Task 7: Wire BacktestPage to multi-symbol routing and accordion results

**Files:**
- Modify: `apps/frontend/src/pages/backtest/BacktestPage.tsx`

- [ ] **Step 1: Replace BacktestPage**

Replace `apps/frontend/src/pages/backtest/BacktestPage.tsx` with:

```typescript
import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import {
  runBacktest,
  runMultiBacktest,
  type BacktestResult,
  type RunMultiBacktestInput,
} from "../../api/backtest";
import BacktestRunForm from "./BacktestRunForm";
import BacktestMetricsCards from "./BacktestMetricsCards";
import BacktestComparisonTable from "./BacktestComparisonTable";
import EquityCurveChart from "./EquityCurveChart";
import BacktestTradeTable from "./BacktestTradeTable";
import AIEvaluationCard from "./AIEvaluationCard";

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
  empty: { color: "text.secondary", textAlign: "center", py: 6 },
  runningInner: {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    gap: 2,
    py: 6,
  },
} as const;

export default function BacktestPage() {
  const [results, setResults] = useState<BacktestResult[]>([]);

  const runM = useMutation({
    mutationFn: async (input: RunMultiBacktestInput) => {
      if (input.symbols.length === 1) {
        const res = await runBacktest({
          symbol: input.symbols[0],
          interval: input.interval,
          strategy_name: input.strategy_name,
          strategy_params: input.strategy_params,
          initial_cash: input.initial_cash,
          position_fraction: input.position_fraction,
          stop_loss_pct: input.stop_loss_pct,
          trail_activation_pct: input.trail_activation_pct,
          trail_pct: input.trail_pct,
          from_ms: input.from_ms,
          to_ms: input.to_ms,
          limit: input.limit,
        });
        return [res];
      }
      const multi = await runMultiBacktest(input);
      return multi.results;
    },
    onMutate: () => setResults([]),
    onSuccess: (res) => setResults(res),
  });

  const errMsg =
    runM.error && typeof runM.error === "object" && "message" in runM.error
      ? String((runM.error as { message: unknown }).message)
      : null;

  const isMulti = results.length > 1;

  return (
    <Box sx={styles.root}>
      <Typography variant="h5" sx={{ fontWeight: 600 }}>
        Backtesting
      </Typography>

      <BacktestRunForm
        onSubmit={(input) => runM.mutate(input)}
        pending={runM.isPending}
      />

      {errMsg ? <Alert severity="error">{errMsg}</Alert> : null}

      {runM.isPending ? (
        <Card>
          <CardContent>
            <Box sx={styles.runningInner}>
              <CircularProgress size={20} />
              <Typography sx={{ color: "text.secondary" }}>
                Replaying historical bars…
              </Typography>
            </Box>
          </CardContent>
        </Card>
      ) : null}

      {!runM.isPending && results.length === 0 ? (
        <Card>
          <CardContent>
            <Typography sx={styles.empty}>
              No backtest runs yet. Configure the form above and press{" "}
              <b>Run Backtest</b>.
            </Typography>
          </CardContent>
        </Card>
      ) : null}

      {isMulti ? (
        <Stack spacing={3}>
          <BacktestComparisonTable results={results} />
          {results.map((r) => (
            <Accordion key={r.config.symbol} disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography sx={{ fontWeight: 600, mr: 2 }}>
                  {r.config.symbol}
                </Typography>
                <Typography
                  sx={{
                    color:
                      Number(r.metrics.total_return) >= 0
                        ? "success.main"
                        : "error.main",
                    fontWeight: 600,
                  }}
                >
                  {(Number(r.metrics.total_return) * 100).toFixed(2)}%
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={3}>
                  <BacktestMetricsCards result={r} />
                  <EquityCurveChart points={r.equity_curve} />
                  <BacktestTradeTable trades={r.trades} />
                </Stack>
              </AccordionDetails>
            </Accordion>
          ))}
        </Stack>
      ) : null}

      {!isMulti && results.length === 1 ? (
        <Stack spacing={3}>
          <BacktestMetricsCards result={results[0]} />
          <EquityCurveChart points={results[0].equity_curve} />
          {results[0].config.strategy_name === "ai" ? (
            <AIEvaluationCard backtestId={results[0].id} />
          ) : null}
          <BacktestTradeTable trades={results[0].trades} />
        </Stack>
      ) : null}
    </Box>
  );
}
```

- [ ] **Step 2: Typecheck**

```bash
cd apps/frontend && pnpm typecheck 2>&1 | head -40
```

Expected: no errors.

- [ ] **Step 3: Run lint**

```bash
cd apps/frontend && pnpm lint 2>&1 | head -30
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/src/pages/backtest/BacktestPage.tsx
git commit -m "feat(backtest): wire multi-symbol routing and accordion results in BacktestPage"
```

---

## Task 8: End-to-end smoke test in the browser

- [ ] **Step 1: Verify backend compiles and tests pass**

```bash
cd apps/backend && go test ./internal/strategy/... ./internal/backtest/... -v 2>&1 | tail -20
```

Expected: all PASS.

- [ ] **Step 2: Open the backtest page**

Navigate to `http://localhost:3000/backtest`.

- [ ] **Step 3: Single-symbol run with MA+RSI Filter**

Set: Symbol = BTCUSDT, Interval = 4h, Strategy = MA + RSI Filter, Bar limit = 500.
Verify: fast=9, slow=21, RSI period=14, buy max=60, sell min=40 are pre-filled.
Click Run Backtest. Expect: KPI summary + equity curve + trade table appear (same layout as before).

- [ ] **Step 4: Change interval and verify preset auto-updates**

With Strategy = MA + RSI Filter, change Interval to 5m.
Verify: fast=5, slow=13, RSI period=10 auto-fill without clicking anything.

- [ ] **Step 5: Multi-symbol run**

Type ETHUSDT into the symbol field and press Enter to add it (now BTCUSDT + ETHUSDT).
Click Run Backtest.
Expect: comparison table appears with two rows; each has an accordion below.
Expand one accordion and verify equity curve + trade table render.

- [ ] **Step 6: Final backend test run**

```bash
cd apps/backend && go test ./... 2>&1 | tail -10
```

Expected: all PASS.
