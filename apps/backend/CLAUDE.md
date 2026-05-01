# Backend (Go)

> Read with root `/CLAUDE.md`. This file = Go-only rules.

## Tech

- Go 1.22+ (use `range over int`)
- HTTP: `chi` (`go-chi/chi/v5`)
- WebSocket (Binance): `gorilla/websocket`
- WebSocket (frontend): `nhooyr/websocket`
- Logging: `log/slog` (JSON in prod, text in dev)
- Config: `viper` (YAML + env override)
- Money: `github.com/shopspring/decimal`
- DB: `pgx/v5` (no ORM). Migrations: `golang-migrate`
- Cache/PubSub: `redis/go-redis/v9`
- Tests: stdlib `testing`, `testify/require`, `testify/mock` only when necessary
- Lint: `golangci-lint` with `errcheck`, `revive`, `gocritic`

## Module layout (one Go module, internal by domain)

```
apps/backend/
├── CLAUDE.md
├── go.mod
├── cmd/
│   ├── api/        # HTTP API gateway
│   ├── bot/        # bot runtime daemon
│   └── migrate/    # DB migrations runner
├── internal/
│   ├── auth/       # req 01_auth_user (deferred)
│   ├── user/       # existing stub — leave alone until needed
│   ├── binance/    # req 02_binance_connector  (rest.go, ws.go, ratelimit.go, types.go)
│   ├── data/       # req 03 + 04  (collector.go, store.go, candles.go)
│   ├── strategy/   # req 05  (engine.go, registry.go, builtin/, types.go)
│   ├── risk/       # req 06  (engine.go, checks.go, policy.go)
│   ├── order/      # req 07  (manager.go, router.go, retry.go)
│   ├── paper/      # req 08
│   ├── backtest/   # req 09
│   ├── tradelog/   # req 10
│   ├── runtime/    # req 11  (controller.go, state.go, pipeline.go)
│   ├── alert/      # req 12
│   ├── api/        # req 13  (server.go, middleware/, handlers/, ws.go)
│   ├── ai/         # client to Python AI service (HTTP)
│   ├── platform/   # config/, logger/, ids/, decimalx/, timex/
│   └── domain/     # cross-package types: symbol, bar, order, position, mode, signal
├── pkg/            # nothing here unless explicitly published
├── config/
│   ├── config.dev.yaml
│   └── strategies/
├── migrations/
│   └── 0001_init.sql
└── test/
    ├── integration/
    └── fixtures/
```

**Mapping rule:** each `trading_bot_requirements_v2/backend-go/NN_*.md` → exactly one `internal/<domain>/` package. Do not collapse.

## Package rules

- `internal/` over `pkg/`.
- One package = one responsibility = one requirement file. >5 files? probably 2 domains.
- Cross-package types in `internal/domain/`. Domain has no internal-package deps.
- `internal/platform/` = infrastructure (logger, config, IDs). Domain depends on platform; platform never depends on domain.

## Conventions

### Error handling

```go
if err := s.binance.PlaceOrder(ctx, o); err != nil {
    return fmt.Errorf("order: place on binance: %w", err)
}

var ErrRiskRejected = errors.New("risk rejected")

if errors.Is(err, risk.ErrRiskRejected) { ... }
```

- Always wrap with `fmt.Errorf("%w", err)` + short context phrase
- Sentinels at package level
- No `panic` outside `main`/`init`

### Context

- Every exported function doing I/O takes `ctx context.Context` as first param
- Pass it down. Never `context.Background()` outside `main`.
- Honor cancellation in long loops: `select { case <-ctx.Done(): return ctx.Err(); ... }`

### Logging

```go
slog.InfoContext(ctx, "order placed",
    "service", "order",
    "mode", string(mode),
    "symbol", o.Symbol,
    "order_id", o.ID,
    "qty", o.Qty.String(),
)
```

- Use `*Context` variants so `request_id` flows in
- Consistent keys: `service`, `mode`, `symbol`, `request_id`, `order_id`, `signal_id`
- No `fmt.Println` / `log.Println`. Tests may use `t.Log`.

### Money

- Never `float64` for prices/qty/equity/P&L
- Compare via `a.LessThan(b)`, `a.Equal(b)` — not `==`
- JSON: marshal as string

### Time

- UTC milliseconds, `int64`
- `internal/platform/timex` provides `NowMs()`, `MsToTime(ms int64) time.Time`
- DB columns: `BIGINT` for ms timestamps (except `created_at` audit rows = `TIMESTAMPTZ`)

### IDs

- ULID via `internal/platform/ids.New() string`, lowercase
- Producer-generated, never DB-generated

### Config

```go
type RiskConfig struct {
    MaxPositionPct      decimal.Decimal `mapstructure:"max_position_pct"`
    MaxDailyDrawdownPct decimal.Decimal `mapstructure:"max_daily_drawdown_pct"`
    MaxSlippageBps      int             `mapstructure:"max_slippage_bps"`
}
```

- Loaded once at startup, validated, passed by value (not pointer) to constructors
- Env override format: `BOT_RISK_MAX_POSITION_PCT=0.02`

## HTTP API

- Routes mounted in `internal/api/server.go`
- One handler file per requirement (`handlers/bot.go`, `handlers/strategy.go`)
- Response shape: `{ "data": ..., "error": null }` or `{ "data": null, "error": { "code": "...", "message": "..." } }`
- Error codes are stable strings: `risk_rejected`, `not_found`, `validation_failed`, `forbidden`
- DTOs next to handlers. Never expose `internal/domain` types directly.
- Middleware order: recover → request_id → logger → auth → cors → route

## Pipeline pattern (the hot path)

`internal/runtime/pipeline.go`:
```
candle → strategy.Engine.OnBar()  → Signal
       → risk.Engine.Validate()    → ValidatedSignal | error
       → order.Manager.Submit()    → Order
       → tradelog.Service.Record(order)
```

Each stage:
- Pure where possible (strategy, risk are pure; order has I/O)
- Explicit types — no `interface{}`
- `Info` on happy path, `Warn` on rejection (with reason), `Error` on system failure

## Testing

- Co-locate `*_test.go` next to source
- Table-driven for `strategy/` and `risk/` (pure → heavy unit coverage)
- `test/integration/` runs full pipeline against fixture candles. Required for changes touching `runtime/`, `strategy/`, `risk/`, `order/`, `paper/`, `backtest/`.
- Mock Binance with local httptest server in `internal/binance/`
- Run: `go test ./...` / `go test -run TestRiskEngine ./internal/risk`
- Coverage: 85% line minimum on `risk/` and `strategy/`

## Build & run

```bash
go mod tidy
go test ./...
go run ./cmd/api          # HTTP API
go run ./cmd/bot          # bot runtime
go run ./cmd/migrate up   # DB migrations
```

## Don'ts

- No `interface{}`/`any` in domain code (allowed in `platform/` for generics shims)
- No global state outside `internal/platform/`
- No goroutine without an exit story (cancellation or done channel)
- No `time.Now()` directly in business logic — use `timex.NowMs()`
- No direct calls to Binance from any package other than `internal/binance/`
- No `os.Exit` outside `main`
- No `init()` for business logic (allowed only for registry registration)
