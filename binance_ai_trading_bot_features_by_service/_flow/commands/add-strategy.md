---
description: Scaffold a new built-in strategy in the Go backend with test
argument-hint: <strategy_name> <symbol> <timeframe>
---

# Add a new strategy

Add a new built-in strategy named `$1` for symbol `$2` at timeframe `$3` to the Go backend.

Read first:
- `CLAUDE.md` (root)
- `apps/backend/CLAUDE.md`
- `apps/backend/internal/strategy/types.go` (if it exists)
- `apps/backend/internal/strategy/builtin/ma_cross.go` (use as reference style if present; otherwise use any existing package under `apps/backend/internal/` like `internal/user/` for general Go style)

Create:
1. `apps/backend/internal/strategy/builtin/$1.go`
   - Implement the `Strategy` interface (constructor + `OnBar(bar) Signal`)
   - Register in `init()` via `registry.Register("$1", New$1)`
   - Reasonable indicator state, properly maintained across bars

2. `apps/backend/internal/strategy/builtin/$1_test.go`
   - Table-driven tests with at least 4 cases: warmup, no-signal, BUY trigger, SELL trigger
   - Use fixture from `apps/backend/test/fixtures/$2_$3_sample.csv` if it exists; otherwise generate inline test bars

3. `apps/backend/config/strategies/$1_$2.yaml`
   - Default parameters for this strategy/symbol pair

After scaffolding (run from `apps/backend/`):
- Run `go test ./internal/strategy/builtin -run Test$1 -v`
- Show me the test output

Do NOT modify the strategy registry, engine, risk, or runtime code.
Do NOT add the strategy to the frontend picker — that's a separate slice.
