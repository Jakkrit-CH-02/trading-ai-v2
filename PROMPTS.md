# Build Prompts — Binance AI Trading Bot

Source of truth for build order: `binance_ai_trading_bot_features_by_service/docs/00_index.md` (Sprint sequence).
Each prompt = one Claude Code session = one commit. Use `/clear` between prompts.

**Path shorthand:** `REQ = binance_ai_trading_bot_features_by_service`

**Rules every session must follow:**
- Read **only** the named requirement file + the named sub-CLAUDE.md. Nothing else.
- Stop at the explicit stop condition. Don't run beyond it.
- Test-first where the prompt says so.
- `sx` prop only on frontend (no `styled`, no `css` prop, no Tailwind).
- Money: `decimal.Decimal` (Go) / `Decimal` (Python) / string in transport. Never `float64`.
- Time: UTC, int64 ms in transport.
- IDs: lowercase ULID.
- Backend router: `chi` (the one "Fiber" mention in `docs/00_index.md` is a doc typo — chi wins per root CLAUDE.md).

---

## Sprint 1 — Foundation

### 1.1 Repo + docker-compose + Makefile

```
Read CLAUDE.md (root) only.
Verify or create at repo root:
- docker-compose.yml: postgres, redis (already exists — confirm services + volumes)
- Makefile: targets `up`, `down`, `test`, `migrate`
- .env.example: BINANCE_API_KEY, BINANCE_API_SECRET, LIVE_TRADING_ENABLED=false, POSTGRES_*, REDIS_*
Stop after `make up` brings up postgres+redis cleanly.
```

### 1.2 Backend skeleton (chi) + shared platform helpers

```
Read REQ/_flow/backend-go.CLAUDE.md and apps/backend/CLAUDE.md only.
Implement under apps/backend/:
- internal/domain/{symbol,bar,order,position,mode,signal}.go
- internal/platform/timex/timex.go (NowMs, MsToTime)
- internal/platform/ids/ids.go (lowercase ULID)
- internal/platform/decimalx/decimalx.go (shopspring/decimal helpers)
- internal/platform/config/config.go (viper: ServerConfig, BinanceConfig, DBConfig, RedisConfig, RiskConfig)
- internal/api/server.go: chi router + middleware (recover, request_id, slog, hardcoded `Authorization: Bearer dev`)
- internal/api/response.go: { data, error } JSON envelope
- internal/storage/postgres/db.go (pgx pool), internal/storage/redis/client.go
- migrations/0001_init.sql (placeholder)
- cmd/api/main.go: wire config -> db -> redis -> server, graceful shutdown
- config/config.dev.yaml (testnet placeholders)
Add only GET /healthz returning {"data":"ok"}.
Stop after `go run ./cmd/api` returns 200 on /healthz.
```

### 1.3 AI service skeleton

```
Read CLAUDE.md (root) only.
Scaffold apps/ai-service/:
- pyproject.toml (uv): fastapi, pydantic v2 + pydantic-settings, pandas, numpy, scikit-learn, polars, joblib, httpx
- app/main.py: FastAPI with GET /healthz
- app/core/{config.py, logging.py (structured)}
- Dockerfile (slim python:3.11)
- Add ai-service to docker-compose.yml
- Create apps/ai-service/CLAUDE.md mirroring apps/backend/CLAUDE.md style: pydantic v2, Decimal for money, never call Binance, all bars come from Go backend over HTTP, structured logging.
Stop after `uv run uvicorn app.main:app` returns 200 on /healthz.
```

### 1.4 Frontend skeleton

```
Read apps/frontend/CLAUDE.md only.
Implement under apps/frontend/src/:
- theme.ts (dark, monospace money font)
- lib/{api.ts (axios + Bearer dev), queryClient.ts, format.ts, msw.ts setup}
- App.tsx + routes.tsx (AppShell + sidebar; placeholder routes /, /market, /bot, /paper, /logs, /risk, /backtest, /ai, /alerts, /settings)
sx prop only, no styled, no css prop.
Stop after `pnpm dev` renders shell with sidebar nav.
```

### 1.5 Shared API contract

```
Read REQ/_flow/CLAUDE.md only.
Document the cross-service envelope in apps/backend/internal/api/response.go and a matching src/lib/api.ts type. Both:
- success: { data: T }
- error: { error: { code: string, message: string, details?: unknown } }
- timestamps int64 ms UTC, money as string ("0.00012345"), ids ULID lowercase
Add an integration test in apps/backend that asserts the envelope on /healthz and on a forced-error endpoint /debug/error.
Stop after tests pass.
```

### 1.6 Health checks (cross-service)

```
Read CLAUDE.md (root) only.
- Backend GET /healthz returns { data: { status, deps: { postgres, redis } } }
- AI service GET /healthz returns { data: { status, model_loaded } }
- Frontend AppShell shows a tiny green/red badge polling both /healthz endpoints (proxy AI through backend at GET /api/ai/healthz).
Stop after both badges turn green with services up, red when one is killed.
```

---

## Sprint 2 — Market Data

### 2.1 Binance Connector

```
Read REQ/backend/02_binance_connector.md and apps/backend/CLAUDE.md only.
Implement internal/binance/:
- rest.go: Client + GetExchangeInfo, GetAccount, PlaceOrder, CancelOrder, GetKlines (testnet/mainnet base URL from config)
- ws.go: KlineStream(symbol, interval) -> <-chan domain.Bar with exponential-backoff reconnect
- ratelimit.go (token bucket), time-sync helper for recvWindow
Tests: httptest server (200 + 429 + 5xx), fake WS asserting reconnect.
Stop after `go test ./internal/binance/...` passes.
```

### 2.2 Market Data Service

```
Read REQ/backend/03_market_data_service.md and apps/backend/CLAUDE.md only.
Implement internal/data/:
- collector/: subscribe to binance.KlineStream, write latest bar to Redis, batch-flush closed bars to Postgres
- market/: read API (Redis hit, Postgres fallback) + chi handlers per the requirement
- migrations/0002_bar_history.sql
Integration test: feed fake bars, assert Redis + Postgres + endpoint shape.
Stop after tests pass.
```

### 2.3 Frontend Market Watch

```
Read REQ/frontend/02_market_watch.md and apps/frontend/CLAUDE.md only.
Implement src/pages/market-watch/ at route /market: symbol list, latest price, sparkline, sort/filter. useQuery refetchInterval 2000.
sx prop only.
Stop after page shows live data from backend.
```

### 2.4 Frontend Dashboard (initial — KPIs only)

```
Read REQ/frontend/01_dashboard.md and apps/frontend/CLAUDE.md only.
Implement src/pages/dashboard/ at route /: 4 KPI cards (equity placeholder until paper lands, today P&L, open positions, bot state). OpenPositionsTable component with empty-state. Wire to whatever endpoints already exist; MSW for any not yet implemented (mark with TODO to switch).
sx prop only.
Stop after dashboard renders.
```

---

## Sprint 3 — AI Data

### 3.1 AI Dataset Builder

```
Read REQ/ai-service/01_dataset_builder.md and apps/ai-service/CLAUDE.md only.
Implement app/datasets/:
- builder.py: pull bars from Go backend market data API (httpx), write parquet to data/datasets/{symbol}_{tf}_{from}_{to}.parquet
- schemas.py: pydantic models
- POST /api/datasets/build, GET /api/datasets
Test: mock backend httpx, build a 100-bar dataset, assert parquet schema.
Stop after `uv run pytest` passes.
```

### 3.2 AI Feature Engineering

```
Read REQ/ai-service/02_feature_engineering.md and apps/ai-service/CLAUDE.md only.
Implement app/features/:
- pipeline.py: deterministic transforms per requirement (returns, EMAs, RSI, volume z-score, etc.)
- registry.py: feature name -> function
- POST /api/features/compute (input: dataset id, output: features parquet path)
Test: snapshot golden output for fixed input.
Stop after tests pass.
```

### 3.3 Frontend AI Training Page (basic form)

```
Read REQ/frontend/06_ai_training_page.md and apps/frontend/CLAUDE.md only.
Implement src/pages/ai-training/ at route /ai with sections: build dataset, compute features. Wire forms to backend proxy endpoints (add internal/api/handlers/ai.go on the Go side: POST /api/ai/datasets/build, /api/ai/features/compute simply forwarding to ai-service).
sx prop only.
Stop after a tiny dataset can be built end-to-end through the UI.
```

---

## Sprint 4 — AI Model

### 4.1 AI Training Pipeline

```
Read REQ/ai-service/03_training_pipeline.md and apps/ai-service/CLAUDE.md only.
Implement app/training/:
- trainer.py: train classifier on features parquet, save model + metadata (features used, metrics, training window)
- POST /api/training/run, GET /api/training/{job_id}
Test: tiny dataset, assert model file produced + metrics structure.
Stop after tests pass.
```

### 4.2 AI Model Registry

```
Read REQ/ai-service/04_model_registry.md and apps/ai-service/CLAUDE.md only.
Implement app/registry/:
- store.py: filesystem registry data/models/{model_id}/ with metadata.json + model.joblib
- service.py: register, list, get, promote (paper/live separation per "Must-have before live trading")
- HTTP: GET /api/models, POST /api/models/{id}/promote
Test: register two versions, promote second to paper then live; assert correct active per environment.
Stop after tests pass.
```

### 4.3 AI Inference API

```
Read REQ/ai-service/05_inference_api.md and apps/ai-service/CLAUDE.md only.
Implement app/inference/:
- service.py: load active model from registry on startup; reload on demand
- POST /api/predict (features payload -> probabilities + decision)
- short-window cache for identical inputs
Test: golden output for fixed feature vector.
Stop after tests pass.
```

### 4.4 AI Signal Explanation

```
Read REQ/ai-service/07_signal_explanation.md and apps/ai-service/CLAUDE.md only.
Implement app/explain/:
- service.py: produce per-prediction feature contributions (SHAP or builtin importance per requirement)
- attach to /api/predict response when ?explain=true
Test: deterministic explanation shape for fixed input.
Stop after tests pass.
```

### 4.5 Frontend AI Training Page (complete)

```
Read REQ/frontend/06_ai_training_page.md and apps/frontend/CLAUDE.md only.
Extend /ai page: training run section, model list, promote action, explanation panel for sample prediction. Add backend proxy handlers for /api/ai/training/*, /api/ai/models/*, /api/ai/predict.
sx prop only.
Stop after end-to-end: build dataset -> features -> train -> promote -> sample predict with explanation.
```

---

## Sprint 5 — Paper Trading Core

### 5.1 Strategy Engine

```
Read REQ/backend/04_strategy_engine.md and apps/backend/CLAUDE.md only.
Implement internal/strategy/:
- types.go: Signal, Reason, RuleConfig
- engine.go: Engine.OnBar(bar) Signal
- registry.go
- builtin/ma_cross.go (EMA9/21), builtin/rsi.go, builtin/ai.go (calls internal/ai/client.go HTTP to inference API)
- internal/ai/client.go (timeout, retry, circuit breaker)
ma_cross_test.go FIRST (warmup, no-cross, cross-up, cross-down, EMA correctness) with inline ~30-bar fixture.
Stop after `go test ./internal/strategy/... ./internal/ai/...` passes.
```

### 5.2 Risk Engine

```
Read REQ/backend/05_risk_engine.md, the "Risk policy" section of root CLAUDE.md, and apps/backend/CLAUDE.md only.
Implement internal/risk/:
- types.go: ValidatedSignal + ErrPositionTooLarge, ErrDailyDrawdown, ErrStopLossRequired, ErrSlippageExceeded
- policy.go: from RiskConfig
- checks.go: Engine.Validate covers checks #1-#4. Live gate (#5) and Kill (#6) wire in Sprint 7.
checks_test.go FIRST: pass case + one rejection per check.
Stop after `go test ./internal/risk/...` passes.
```

### 5.3 Order Manager

```
Read REQ/backend/06_order_manager.md and apps/backend/CLAUDE.md only.
Implement internal/order/:
- manager.go: Manager.Submit(ctx, ValidatedSignal) -> Order
- router.go: route by mode — paper -> paper.Engine, live -> binance.Client (live returns ErrLiveDisabled until Sprint 7)
- backtest mode hooks added later
Integration test: mocked paper engine receives orders.
Stop after tests pass.
```

### 5.4 Paper Trading Engine

```
Read REQ/backend/07_paper_trading_engine.md and apps/backend/CLAUDE.md only.
Implement internal/paper/engine.go: simulate fill at bar.Close + 1bp spread, virtual balance, open positions, P&L, emit TradeLog event channel.
Integration test: 5 mixed signals -> assert final balance + open positions.
Stop after tests pass.
```

### 5.5 Trade Log Service

```
Read REQ/backend/11_trade_log_service.md and apps/backend/CLAUDE.md only.
Implement internal/tradelog/:
- service.go: Record, List(filter), Summary(period)
- subscribe to paper.Engine TradeLog channel and (later) live order events
- migrations/0003_trade_log.sql
- HTTP: GET /api/trades, GET /api/trades/summary
Test: insert sample rows; filter+pagination+summary.
Stop after tests pass.
```

### 5.6 Bot Runtime Manager

```
Read REQ/backend/12_bot_runtime_manager.md and apps/backend/CLAUDE.md only.
Implement internal/runtime/:
- state.go: FSM (idle, running, paused, halted)
- controller.go: Start/Stop/Pause/Kill (Kill = stub until Sprint 7)
- pipeline.go: data -> strategy -> risk -> order -> tradelog
- HTTP: /api/bot/{start,stop,pause,status}
- graceful SIGINT shutdown
Test: race-checked shutdown <5s, no leaked goroutines; full pipeline test with fixture bars.
Stop after tests pass.
```

### 5.7 Frontend Bot Control

```
Read REQ/frontend/03_bot_control.md and apps/frontend/CLAUDE.md only.
Implement src/pages/bot-control/ at /bot: ModeSelector (live disabled + tooltip), StrategyPicker (ma_cross, rsi, ai), SymbolTimeframePicker, RiskFormFields. react-hook-form + zod. POST /api/bot/start.
sx prop only.
Stop after Start submits and runtime moves to running.
```

### 5.8 Frontend Paper Trading

```
Read REQ/frontend/07_paper_trading_page.md and apps/frontend/CLAUDE.md only.
Implement src/pages/paper-trading/ at /paper: virtual balance, open positions, recent fills, P&L curve. Poll 2s.
sx prop only.
Stop after page reflects real paper-trade activity.
```

### 5.9 Frontend Trade Logs

```
Read REQ/frontend/04_trade_logs.md and apps/frontend/CLAUDE.md only.
Implement src/pages/trade-logs/ at /logs: filterable, paginated table; CSV export button.
sx prop only.
Stop after page renders with filters and pagination.
```

### 5.10 Frontend Risk Monitor

```
Read REQ/frontend/08_risk_monitor.md and apps/frontend/CLAUDE.md only.
Implement src/pages/risk-monitor/ at /risk. Add backend GET /api/risk/snapshot in internal/risk/handlers.go reading from runtime state.
sx prop only.
Stop after page shows current exposure, drawdown, slippage stats live.
```

**Sprint 5 acceptance:** /bot Start (paper, ma_cross, BTCUSDT, 1m) → /paper updates → /logs shows trades → run 30 min on testnet without crash.

---

## Sprint 6 — Backtesting

### 6.1 Backtest Engine

```
Read REQ/backend/08_backtest_engine.md and apps/backend/CLAUDE.md only.
Implement internal/backtest/:
- engine.go: replay bars from internal/data/market over strategy + risk; simulate fills at bar.Close (no spread); produce BacktestResult (equity curve, trades, P&L, drawdown, sharpe, win rate)
- store.go: persist result
- migrations/0004_backtest_results.sql
- HTTP: POST /api/backtest/run, GET /api/backtest, GET /api/backtest/{id}
Integration test: small fixture range -> deterministic result -> assert metrics.
Stop after tests pass.
```

### 6.2 AI Backtest Evaluation

```
Read REQ/ai-service/06_backtest_ai_evaluation.md and apps/ai-service/CLAUDE.md only.
Implement app/evaluation/:
- service.py: pull backtest result from Go backend, compute model-level metrics (precision, recall, calibration, feature drift) per requirement
- POST /api/evaluation/run (input: backtest_id, model_id), GET /api/evaluation/{id}
Test: fixture backtest input -> deterministic eval payload.
Stop after tests pass.
```

### 6.3 Frontend Backtesting Result

```
Read REQ/frontend/05_backtesting_result.md and apps/frontend/CLAUDE.md only.
Implement src/pages/backtest/ at /backtest: launch form (strategy, range, params), equity curve (recharts), trades table, KPI summary, "Evaluate AI" button calling /api/ai/evaluation/run when strategy=ai.
sx prop only.
Stop after a backtest can be launched and rendered, including AI evaluation when applicable.
```

---

## Sprint 7 — Live Safety

### 7.1 Auth / User

```
Read REQ/backend/01_auth_user.md and apps/backend/CLAUDE.md only.
Implement internal/auth/:
- service.go: bcrypt + JWT, users table (with role: admin/operator)
- middleware.go: replace hardcoded Bearer dev with real JWT verification + role guard
- HTTP: POST /api/auth/{login,logout,register}, GET /api/auth/me
- migrations/0005_users.sql
Frontend: src/pages/login + token store (Zustand) + axios interceptor + route guard.
Test: register/login + protected route + admin-only route.
Stop after tests pass and frontend can log in.
```

### 7.2 Settings Service

```
Read REQ/backend/09_settings_service.md and apps/backend/CLAUDE.md only.
Implement internal/settings/:
- service.go: read/write user-scoped settings (risk thresholds, notification prefs, default symbol/tf), backed by Postgres
- migrations/0006_settings.sql
- HTTP: GET/PUT /api/settings (admin can edit global; operator can edit own)
Test: round-trip + role enforcement.
Stop after tests pass.
```

### 7.3 Alert Service

```
Read REQ/backend/10_alert_service.md and apps/backend/CLAUDE.md only.
Implement internal/alert/:
- service.go: rules (drawdown breach, order rejection, disconnect, slippage exceeded, kill triggered) + pluggable Notifier (stdout + DB persistence first)
- migrations/0007_alerts.sql
- HTTP: GET /api/alerts, POST /api/alerts/{id}/ack
- subscribe to runtime + risk + binance disconnect events
Test: trigger each rule type -> row inserted.
Stop after tests pass.
```

### 7.4 Frontend Settings

```
Read REQ/frontend/09_settings.md and apps/frontend/CLAUDE.md only.
Implement src/pages/settings/ at /settings: risk thresholds, notification prefs, API key status display, model selection (paper vs live).
sx prop only.
Stop after change persists across reload.
```

### 7.5 Frontend Alert Center

```
Read REQ/frontend/10_alert_center.md and apps/frontend/CLAUDE.md only.
Implement src/pages/alerts/ at /alerts: list, filter, ack. Toast subscriber polling /api/alerts every 5s for new unacked.
sx prop only.
Stop after ack flow works.
```

### 7.6 Live Trading Gate + Kill Switch (final)

```
Read REQ/backend/05_risk_engine.md, REQ/backend/06_order_manager.md, REQ/backend/12_bot_runtime_manager.md, root CLAUDE.md "Risk policy", and apps/backend/CLAUDE.md only.
Implement:
- order/router.go: live route enabled only if (a) mode=live, (b) env LIVE_TRADING_ENABLED=true, (c) startup-time Binance API key permission check passed (no withdraw, has trade), (d) request carries valid live-confirmation token issued from UI modal
- runtime/controller.go: Kill — POST /api/bot/kill cancels all open orders via binance, flattens positions, transitions to halted, blocks Start until /api/bot/reset by admin
- audit log: every live submit + Kill action recorded to a new audit_log table (migrations/0008_audit_log.sql)
- frontend /bot: live mode confirmation modal (typed phrase "I UNDERSTAND THE RISK"), big red Kill button visible whenever state != idle, admin role guard
Integration test: gate denies live without each condition individually; Kill flattens; audit rows created.
Stop after tests pass and a manual testnet live run with all conditions on works.
```

---

## Progress checklist

- [ ] 1.1  Repo + docker-compose + Makefile
- [ ] 1.2  Backend skeleton
- [ ] 1.3  AI service skeleton
- [ ] 1.4  Frontend skeleton
- [ ] 1.5  Shared API contract
- [ ] 1.6  Health checks
- [ ] 2.1  Binance Connector
- [ ] 2.2  Market Data Service
- [ ] 2.3  Frontend Market Watch
- [ ] 2.4  Frontend Dashboard (initial)
- [ ] 3.1  AI Dataset Builder
- [ ] 3.2  AI Feature Engineering
- [ ] 3.3  Frontend AI Training Page (basic)
- [ ] 4.1  AI Training Pipeline
- [ ] 4.2  AI Model Registry
- [ ] 4.3  AI Inference API
- [ ] 4.4  AI Signal Explanation
- [ ] 4.5  Frontend AI Training Page (complete)
- [ ] 5.1  Strategy Engine
- [ ] 5.2  Risk Engine
- [ ] 5.3  Order Manager
- [ ] 5.4  Paper Trading Engine
- [ ] 5.5  Trade Log Service
- [ ] 5.6  Bot Runtime Manager
- [ ] 5.7  Frontend Bot Control
- [ ] 5.8  Frontend Paper Trading
- [ ] 5.9  Frontend Trade Logs
- [ ] 5.10 Frontend Risk Monitor
- [ ] 6.1  Backtest Engine
- [ ] 6.2  AI Backtest Evaluation
- [ ] 6.3  Frontend Backtesting Result
- [ ] 7.1  Auth / User
- [ ] 7.2  Settings Service
- [ ] 7.3  Alert Service
- [ ] 7.4  Frontend Settings
- [ ] 7.5  Frontend Alert Center
- [ ] 7.6  Live Trading Gate + Kill Switch
