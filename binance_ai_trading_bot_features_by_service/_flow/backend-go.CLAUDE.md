# Backend Go

> Read together with the root `/CLAUDE.md`. This file covers Go-only rules.

## Tech

- Go 1.22+ (use the `range over int` syntax)
- HTTP: `chi` router (`go-chi/chi/v5`)
- WebSocket (Binance): `gorilla/websocket`
- WebSocket (frontend): `nhooyr/websocket`
- Logging: stdlib `log/slog` with JSON handler in production, text handler in dev
- Config: `viper` reading YAML + env override
- Money: `github.com/shopspring/decimal`
- DB: `pgx/v5` (no ORM). Migrations: `golang-migrate`
- Cache/PubSub: `redis/go-redis/v9`
- Tests: stdlib `testing`, `testify/require` for assertions, `testify/mock` only when necessary
- Lint: `golangci-lint` with default + `errcheck`, `revive`, `gocritic`

## Module layout (one Go module, internal packages by domain)

```
apps/backend-go/
├── CLAUDE.md
├── go.mod
├── go.sum
├── cmd/
│   ├── api/                      # HTTP API gateway
│   │   └── main.go
│   ├── bot/                      # bot runtime daemon
│   │   └── main.go
│   └── migrate/                  # DB migrations runner
│       └── main.go
├── internal/
│   ├── auth/                     # req 01_auth_user
│   ├── binance/                  # req 02_binance_connector
│   │   ├── rest.go
│   │   ├── ws.go
│   │   ├── ratelimit.go
│   │   └── types.go
│   ├── data/                     # req 03_data_collector + 04_market_data_service
│   │   ├── collector.go
│   │   ├── store.go              # postgres + redis
│   │   └── candles.go
│   ├── strategy/                 # req 05_strategy_engine
│   │   ├── engine.go
│   │   ├── registry.go
│   │   ├── builtin/              # ma_cross.go, rsi_ema.go, ...
│   │   └── types.go              # Signal, Reason, Bar
│   ├── risk/                     # req 06_risk_engine
│   │   ├── engine.go
│   │   ├── checks.go             # position, drawdown, slippage, stop required
│   │   └── policy.go             # loaded from config
│   ├── order/                    # req 07_order_manager
│   │   ├── manager.go
│   │   ├── router.go             # paper vs live
│   │   └── retry.go
│   ├── paper/                    # req 08_paper_trading_engine
│   ├── backtest/                 # req 09_backtesting_engine
│   ├── tradelog/                 # req 10_trade_log_service
│   ├── runtime/                  # req 11_bot_runtime_controller
│   │   ├── controller.go         # start/stop/pause/kill
│   │   ├── state.go              # FSM
│   │   └── pipeline.go           # data -> strategy -> risk -> order
│   ├── alert/                    # req 12_alert_service
│   ├── api/                      # req 13_api_gateway
│   │   ├── server.go             # chi router setup
│   │   ├── middleware/
│   │   ├── handlers/             # one file per route group
│   │   └── ws.go                 # frontend WS
│   ├── ai/                       # client to Python AI service (HTTP)
│   │   └── client.go
│   ├── platform/
│   │   ├── config/               # viper loader, schema
│   │   ├── logger/
│   │   ├── ids/                  # ULID
│   │   ├── decimalx/             # decimal helpers
│   │   └── timex/                # UTC ms helpers
│   └── domain/                   # cross-package types
│       ├── symbol.go
│       ├── bar.go
│       ├── order.go
│       ├── position.go
│       └── mode.go               # Mode enum: backtest, paper, live
├── pkg/                          # nothing here unless we explicitly publish
├── config/
│   ├── config.yaml
│   ├── config.dev.yaml
│   └── strategies/
│       └── ma_cross_btcusdt.yaml
├── migrations/
│   └── 0001_init.sql
└── test/
    ├── integration/              # full pipeline tests
    └── fixtures/                 # sample candles for backtest
```

**Mapping rule:** each file in `../trading_bot_requirements_v2/backend-go/NN_*.md` corresponds to exactly one `internal/<domain>/` package. Do not collapse multiple requirements into one package.

## Package rules

- `internal/` over `pkg/`. Anything reachable from outside our module is intentional.
- One package = one responsibility = one requirement file. If a package needs >5 files, consider whether it's actually two domains.
- Cross-package types live in `internal/domain/`. Domain types have no dependencies on other internal packages.
- `internal/platform/` holds infrastructure helpers (logger, config, IDs). Domain code depends on platform; platform never depends on domain.

## Conventions

### Error handling
```go
// Wrap with context
if err := s.binance.PlaceOrder(ctx, o); err != nil {
    return fmt.Errorf("order: place on binance: %w", err)
}

// Sentinels for branching
var ErrRiskRejected = errors.New("risk rejected")

// Check
if errors.Is(err, risk.ErrRiskRejected) { ... }
```

- Always wrap with `fmt.Errorf("%w", err)` and a short context phrase
- Sentinel errors at the package level (`var ErrFoo = errors.New("foo")`)
- No `panic` outside `main` and `init`

### Context
- Every exported function that does I/O takes `ctx context.Context` as first param
- Pass it down. Never use `context.Background()` outside `main`.
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

- Use `*Context` variants so `request_id` from middleware flows in
- Keys: `service`, `mode`, `symbol`, `request_id`, `order_id`, `signal_id` — consistent across packages
- No `fmt.Println`. No `log.Println`. Tests may use `t.Log`.

### Money / decimals
```go
import "github.com/shopspring/decimal"

var maxPosPct = decimal.NewFromFloat(0.02)
```

- Never `float64` for prices, qty, equity, P&L
- Comparisons: `a.LessThan(b)`, `a.Equal(b)`. Don't compare via `==`.
- Transport JSON: `Marshal`/`Unmarshal` as string

### Time
- All timestamps in UTC milliseconds, type `int64`
- `internal/platform/timex` provides `NowMs()`, `MsToTime(ms int64) time.Time`
- DB columns: `BIGINT` for ms timestamps, not `TIMESTAMPTZ`, except `created_at` for audit rows

### IDs
- ULID via `internal/platform/ids.New()` returns `string`
- Lowercase. Generated by the producer (do not let the DB generate IDs).

### Config
```go
type Config struct {
    Binance  BinanceConfig
    Risk     RiskConfig
    Mode     domain.Mode
}

type RiskConfig struct {
    MaxPositionPct      decimal.Decimal `mapstructure:"max_position_pct"`
    MaxDailyDrawdownPct decimal.Decimal `mapstructure:"max_daily_drawdown_pct"`
    MaxSlippageBps      int             `mapstructure:"max_slippage_bps"`
}
```

- Loaded once at startup, validated, then passed by value (not by pointer) to constructors
- Env override format: `BOT_RISK_MAX_POSITION_PCT=0.02`

## HTTP API conventions

- Routes mounted in `internal/api/server.go`
- One handler file per requirement (`handlers/bot.go`, `handlers/strategy.go`, etc.)
- Response shape: `{ "data": ..., "error": null }` on success, `{ "data": null, "error": { "code": "...", "message": "..." } }` on failure
- Error codes are stable strings (`risk_rejected`, `not_found`, `validation_failed`, `forbidden`)
- DTOs live next to handlers, never expose `internal/domain` types directly via JSON
- Middleware order: recover → request_id → logger → auth → cors → route

## Pipeline pattern (the hot path)

The bot runtime in `internal/runtime/pipeline.go` runs:
```
candle → strategy.Engine.OnBar() → Signal
       → risk.Engine.Validate(signal) → ValidatedSignal | error
       → order.Manager.Submit(validatedSignal) → Order
       → tradelog.Service.Record(order)
```

Each stage:
- Pure where possible (strategy, risk are pure; order has I/O)
- Returns explicit types — no `interface{}`
- Logs at `Info` on the happy path, `Warn` on rejection (with reason), `Error` on system failure

## Testing

- Co-locate `*_test.go` next to source
- Table-driven tests for strategy and risk (these are pure and deserve heavy unit coverage)
- `test/integration/` runs the full pipeline against fixture candles. Required for: any change touching `runtime`, `strategy`, `risk`, `order`, `paper`, `backtest`.
- Mock Binance with a local httptest server in `internal/binance/binance_test.go`
- Run: `go test ./...` (full) / `go test -run TestRiskEngine ./internal/risk` (focused)
- Coverage gates only on `risk/` and `strategy/`: 85% line minimum

## Build & run

```bash
go mod tidy
go build ./...
go test ./...
go run ./cmd/api          # HTTP API
go run ./cmd/bot          # bot runtime
go run ./cmd/migrate up   # DB migrations
```

## Don'ts (Go-specific)

- No `interface{}` / `any` in domain code (allowed in `platform/` for generics shims)
- No global state outside `internal/platform/`
- No goroutine without an exit story (cancellation or done channel)
- No `time.Now()` directly in business logic — go through `timex.NowMs()` so tests can override
- No direct calls to Binance from any package other than `internal/binance/`
- No `os.Exit` outside `main`
- No `init()` functions for business logic (allowed only for registering things into a registry)
