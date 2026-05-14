# Binance AI Trading Bot

**Language / ภาษา:** [English](#binance-ai-trading-bot) | [ภาษาไทย](#binance-ai-trading-bot-ภาษาไทย)

Automated cryptocurrency trading system for Binance with rule-based and AI-driven strategies, a risk engine, paper/live/backtest modes, and a full operator UI.

## Architecture

```
[Frontend (React/Vite/TS)]  ──HTTPS/WS──>  [Backend (Go)]  ──HTTP──>  [AI Service (Python)]
        :3000 / :5173                           :8080                        :8001
                                                  │
                                                  └──REST/WS──>  [Binance API]
```

| Service | Tech | Role |
|---------|------|------|
| **Frontend** | React 18, Vite, TypeScript, MUI v5 | Operator dashboard, bot control, charts, alerts |
| **Backend** | Go 1.22+, chi router, pgx, slog | Market data, strategies, risk, orders, auth, bot runtime |
| **AI Service** | Python 3.11+, FastAPI, scikit-learn | Dataset building, feature engineering, training, inference |
| **PostgreSQL 16** | — | Trades, bars, users, settings, alerts, audit log |
| **Redis 7** | — | Market data cache, pub/sub |

The Go backend is the **only** service that talks to Binance. Neither the frontend nor the AI service calls Binance directly.

---

## Trading Modes

| Mode | Description | Risk |
|------|-------------|------|
| **Backtest** | Replays historical candles through strategies. No real or virtual money at stake. Used to evaluate strategy performance before going live. | None |
| **Paper** | Connects to Binance **testnet** WebSocket for real-time prices but executes trades in a virtual portfolio (simulated fills). Identical pipeline to live mode. | None (virtual cash) |
| **Live** | Connects to Binance **mainnet** and submits real orders. Gated by a three-step safety check (UI confirmation + env var + API key validation). | Real money |

---

## Features by Page

### Dashboard (`/`)
- **Portfolio summary** — balance, equity, daily P&L, current drawdown percentage.
- **Open positions** — symbol, quantity, average entry price, current price, unrealized P&L.
- **Latest AI signal** — action (buy/sell/hold), confidence score, generating strategy, timestamp.
- **System health** — live status badges for Binance REST, Binance WS, AI service, database, and Redis.
- **Recent alerts** — the latest alerts with severity and message.

### Market Watch (`/market`)
- Real-time prices for tracked symbols with sparkline mini-charts.
- 24-hour price change percentage, volume, and bid-ask spread.
- Prices update via Binance WebSocket streams.

### Bot Control (`/bot`)
- **Mode selector** — switch between backtest, paper, and live. Selecting live triggers a confirmation modal.
- **Strategy picker** — choose from `ma_cross` (moving average crossover), `rsi`, or `ai` (ML model).
- **Symbol & timeframe** — select the trading pair (e.g., BTCUSDT) and candle interval (1m, 5m, 15m, 1h, etc.).
- **Risk config** — override max position size, daily drawdown limit, slippage cap, and stop-loss requirement per run.
- **Runtime controls** — start, pause, resume, stop, and kill-switch buttons. Status chip shows idle/running/paused/halted.

### Paper Trading (`/paper`)
- Virtual portfolio with configurable initial cash balance.
- Position table with mark-to-market values and unrealized P&L.
- Full trade history with side, quantity, fill price, fees, and realized P&L.
- Equity curve chart tracking portfolio value over time.
- Reset button to clear positions and restart with fresh cash.

### Trade Logs (`/logs`)
- Complete history of every trade across all modes (paper, backtest, live).
- Filterable by symbol, date range, mode, and side (buy/sell).
- Columns: timestamp, symbol, side, quantity, fill price, fee, realized P&L, cash balance after trade.

### Risk Monitor (`/risk`)
- **Position exposure** — current position sizes as a percentage of equity vs. the configured maximum.
- **Daily drawdown** — realized + unrealized loss today vs. the configured maximum.
- **Slippage** — latest observed slippage vs. the configured maximum (basis points).
- Warning banner when any limit is breached. The bot auto-halts on daily drawdown breach.

### Backtesting (`/backtest`)
- Configure: symbol, timeframe, date range, strategy, and initial cash.
- Results: total return, Sharpe ratio, max drawdown, win rate, profit factor.
- Trade list with entry/exit prices and P&L per trade.
- Equity curve chart.
- AI evaluation metrics (accuracy, precision, recall) when using the AI strategy.

### AI Training (`/ai`)
- **Build dataset** — select symbol, timeframe, date range, and label type (next-candle direction, future return, or threshold). Data is fetched from the backend's bar history.
- **Compute features** — run feature engineering (RSI, EMA, MACD, volume ratio, volatility, trend strength) on a dataset.
- **Train model** — choose model type (random forest, logistic regression, XGBoost, LightGBM), set hyperparameters, and launch a training job.
- **Model registry** — view all trained models with version, metrics (accuracy, precision, recall, F1, AUC), and promote one to "active" for inference.
- **Predict / explain** — send features to the active model and see the predicted signal, confidence, risk score, and feature importance breakdown.

### Alerts (`/alerts`)
- Alert types: `drawdown_breach`, `order_rejection`, `binance_disconnect`, `slippage_exceeded`, `kill_triggered`.
- Severities: info, warning, critical.
- Mark individual or all alerts as read.

### Settings (`/settings`)
- Binance API key status (testnet vs. mainnet, key permissions).
- Risk parameter form (max position %, max daily drawdown %, max slippage bps, require stop loss).
- Notification preferences (which alert severities trigger notifications).

---

## Risk Engine

Every order in every mode (backtest, paper, live) passes through these checks before execution. Violations produce hard errors, not warnings.

| Rule | Default | What it does |
|------|---------|--------------|
| **Position sizing** | 2% of equity | Rejects any order whose notional value exceeds this percentage of portfolio equity. |
| **Daily drawdown** | 5% of equity | Halts the bot if the sum of realized and unrealized losses for the day exceeds this threshold. |
| **Stop-loss required** | Enabled | Every order must have an associated stop-loss price. Orders without one are rejected. |
| **Slippage check** | 30 bps | Market orders compute expected slippage from order-book depth. Orders exceeding this limit are rejected. |
| **Live trading gate** | — | Switching to live requires: (1) explicit UI confirmation dialog, (2) `LIVE_TRADING_ENABLED=true` env var, (3) successful Binance API key validation. Missing any one blocks the switch. |
| **Kill switch** | — | `POST /api/bot/kill` cancels all open orders, flattens all positions, and disables further entries until manually re-enabled. |

---

## Strategies

| Strategy | How it works |
|----------|-------------|
| `ma_cross` | Moving average crossover. Generates a BUY signal when the fast MA crosses above the slow MA, SELL when it crosses below. |
| `rsi` | RSI-based. Generates BUY when RSI drops below the oversold threshold, SELL when it rises above the overbought threshold. |
| `ai` | Calls the Python AI service for inference. The active ML model returns a signal (buy/sell/hold) with a confidence score. Falls back to HOLD if the model is unavailable. |

The strategy engine evaluates all configured strategies on each incoming bar. The first non-HOLD signal wins. If all strategies return HOLD, no action is taken.

---

## Trading Pipeline

```
Bar arrives (WebSocket / historical)
       │
       ▼
  Strategy.OnBar(bar)  →  Signal { action, strength, reason }
       │
       ▼
  Risk.Validate(signal, equity, dailyPnL)  →  ValidatedSignal  or  rejection + alert
       │
       ▼
  OrderManager.Submit(validatedSignal)  →  Order { symbol, side, qty, price, stopPrice }
       │
       ▼
  Router dispatches to executor:
    ├── Paper  →  simulated fill (close ± 1bp spread)
    ├── Live   →  Binance REST API order
    └── Backtest  →  historical fill simulator
       │
       ▼
  TradeLog.Record(fill)  →  persisted to PostgreSQL
```

---

## Backend API Endpoints

### Auth (public)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/auth/register` | Register a new user |
| POST | `/api/auth/login` | Login, returns JWT |
| POST | `/api/auth/logout` | Logout |
| GET | `/api/auth/me` | Current user profile |

### Bot Control (authenticated)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/bot/start` | Start bot with mode, strategy, symbol |
| POST | `/api/bot/stop` | Stop bot gracefully |
| POST | `/api/bot/pause` | Pause bot |
| POST | `/api/bot/resume` | Resume bot |
| POST | `/api/bot/kill` | Kill switch — cancel all, flatten, halt |
| GET | `/api/bot/status` | Runtime state (idle/running/paused/halted) |

### Data & Trading
| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/settings` | Get user settings |
| PUT | `/api/settings` | Update settings |
| GET | `/api/alerts` | List alerts |
| POST | `/api/alerts/{id}/ack` | Acknowledge alert |

### AI Proxy (backend forwards to Python)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/ai/datasets/build` | Build labeled dataset from bars |
| POST | `/api/ai/features/compute` | Compute feature vectors |
| POST | `/api/ai/training/run` | Start training job |
| GET | `/api/ai/training/{id}` | Training job status |
| GET | `/api/ai/models` | List models + active model |
| POST | `/api/ai/models/{id}/promote` | Promote model to active |
| POST | `/api/ai/predict` | Get inference prediction |
| POST | `/api/ai/predict/reload` | Reload active model |

### Health
| Method | Path | Description |
|--------|------|-------------|
| GET | `/healthz` | Backend health |
| GET | `/api/ai/healthz` | AI service health |

---

## AI Service Detail

### Inference Response

When the active model receives a prediction request, it returns:

| Field | Type | Description |
|-------|------|-------------|
| `signal` | string | `BUY`, `SELL`, or `HOLD` |
| `confidence` | float | 0.0–1.0, model's confidence in the signal |
| `risk_score` | float | 0.0–1.0, estimated risk level |
| `probabilities` | object | Per-class probabilities (`{"buy": 0.76, "sell": 0.12, "hold": 0.12}`) |
| `model_id` | string | ULID of the model that produced the prediction |
| `model_version` | int | Model version number |
| `reason` | string | Human-readable explanation (e.g., "EMA trend positive, RSI not overbought") |

If no model is loaded, the service returns `HOLD` with confidence 0.0 and risk_score 1.0.

### Supported Model Types
- **Random Forest** (scikit-learn) — default, good baseline
- **Logistic Regression** — fast, interpretable
- **XGBoost** — gradient boosting (optional dependency)
- **LightGBM** — gradient boosting (optional dependency)

### Feature Set
RSI (14-period), EMA (20, 50, 200), MACD, volume ratio, volatility, trend strength. Features are computed from OHLCV bars and saved as Parquet files.

---

## Database Schema

Eight migration files in `apps/backend/migrations/`:

| Migration | Tables | Purpose |
|-----------|--------|---------|
| `0001_init` | `schema_meta` | Metadata / phase tracking |
| `0002_bar_history` | `bars` | OHLCV candle storage with composite index on (symbol, interval, open_time) |
| `0003_trade_log` | `trade_log` | Every executed trade: mode, symbol, side, qty, fill price, fee, realized P&L, cash after |
| `0004_backtest_results` | backtest tables | Backtest run configs and results |
| `0005_users` | `users` | Auth: username, password hash, role (admin/operator/viewer) |
| `0006_settings` | settings tables | User settings, risk params, notification prefs |
| `0007_alerts` | `alerts` | Alert history with type, severity, read status |
| `0008_audit_log` | audit tables | Audit trail for sensitive actions |

---

## Configuration

### Backend (`apps/backend/config/config.dev.yaml`)

```yaml
env: dev
mode: paper

server:
  host: 0.0.0.0
  port: 8080

binance:
  base_url: https://testnet.binance.vision
  ws_url: wss://stream.testnet.binance.vision
  api_key: ""        # set via BOT_BINANCE_API_KEY env var
  api_secret: ""     # set via BOT_BINANCE_API_SECRET env var
  testnet: true

db:
  dsn: postgres://postgres:postgres@localhost:5432/trading?sslmode=disable
  max_conns: 10
  min_conns: 1
  conn_max_lifetime_sec: 1800

redis:
  addr: localhost:6379
  password: ""
  db: 0

risk:
  max_position_pct: "0.02"
  max_daily_drawdown_pct: "0.05"
  max_slippage_bps: 30
  require_stop_loss: true
```

All fields can be overridden with environment variables using the `BOT_` prefix (e.g., `BOT_RISK_MAX_POSITION_PCT=0.03`).

### AI Service

Configured via environment variables with `AI_` prefix:

| Variable | Default | Description |
|----------|---------|-------------|
| `AI_ENV` | `dev` | Environment |
| `AI_LOG_LEVEL` | `INFO` | Log level |
| `AI_HOST` | `0.0.0.0` | Listen host |
| `AI_PORT` | `8001` | Listen port |
| `AI_BACKEND_BASE_URL` | `http://backend:8080` | Go backend URL for fetching bar data |
| `AI_BACKEND_TIMEOUT_S` | `10.0` | HTTP timeout for backend calls |

---

## Prerequisites

Before running the system, ensure you have:

1. **Binance Testnet Account** — register at [testnet.binance.vision](https://testnet.binance.vision) to get API keys for paper trading. No API keys are needed for backtesting.
2. **Binance Mainnet Account** (only for live trading) — mainnet API keys with spot trading permission. Keep `LIVE_TRADING_ENABLED=true` unset until you are ready.
3. **Docker & Docker Compose** — for the containerized setup.
4. **Or local toolchains** — Go 1.22+, Python 3.11+ with uv, Node.js 18+ with pnpm, PostgreSQL 16, Redis 7.

---

## Getting Started

### Docker Compose (recommended)

```bash
# Clone and start all services
git clone <repo-url> && cd trading-ai-v2
docker compose up --build

# Services:
#   Frontend   → http://localhost:3000
#   Backend    → http://localhost:8080
#   AI Service → http://localhost:8001
#   PostgreSQL → localhost:5432
#   Redis      → localhost:6379
```

### Local Development

```bash
# 1. Start infrastructure
docker compose up postgres redis

# 2. Run database migrations
cd apps/backend
for f in migrations/*.sql; do
  psql -h localhost -U postgres -d trading -f "$f"
done

# 3. Start backend
go run ./cmd/api -config config/config.dev.yaml

# 4. Start AI service
cd apps/ai-service
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001

# 5. Start frontend
cd apps/frontend
pnpm install
pnpm dev
# → http://localhost:5173
```

---

## Environment Variables Reference

### Backend

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `BOT_ENV` | `dev` | No | Environment (dev/staging/prod) |
| `BOT_MODE` | `paper` | No | Default trading mode |
| `BOT_SERVER_HOST` | `0.0.0.0` | No | HTTP listen host |
| `BOT_SERVER_PORT` | `8080` | No | HTTP listen port |
| `BOT_DB_DSN` | (see config) | Yes | PostgreSQL connection string |
| `BOT_REDIS_ADDR` | `localhost:6379` | Yes | Redis address |
| `BOT_AI_SERVICE_URL` | `http://ai-service:8001` | Yes | AI service URL |
| `BOT_BINANCE_API_KEY` | — | For paper/live | Binance API key |
| `BOT_BINANCE_API_SECRET` | — | For paper/live | Binance API secret |
| `BOT_BINANCE_TESTNET` | `true` | No | Use Binance testnet |
| `BOT_RISK_MAX_POSITION_PCT` | `0.02` | No | Max position size (fraction) |
| `BOT_RISK_MAX_DAILY_DRAWDOWN_PCT` | `0.05` | No | Max daily drawdown (fraction) |
| `BOT_RISK_MAX_SLIPPAGE_BPS` | `30` | No | Max slippage in basis points |
| `BOT_RISK_REQUIRE_STOP_LOSS` | `true` | No | Require stop-loss on every order |
| `LIVE_TRADING_ENABLED` | `false` | For live | Must be `true` to enable live trading |

### AI Service

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `AI_ENV` | `dev` | No | Environment |
| `AI_LOG_LEVEL` | `INFO` | No | Log level |
| `AI_HOST` | `0.0.0.0` | No | Listen host |
| `AI_PORT` | `8001` | No | Listen port |
| `AI_BACKEND_BASE_URL` | `http://backend:8080` | Yes | Backend URL for bar data |
| `AI_BACKEND_TIMEOUT_S` | `10.0` | No | Backend HTTP timeout (seconds) |

---

## User Roles

| Role | Permissions |
|------|-------------|
| **admin** | Full control: manage users, modify settings, control bot, view all data |
| **operator** | Control bot (start/stop/pause), view data, cannot modify system settings |
| **viewer** | Read-only access to dashboard, positions, trade logs, and alerts |

---

## Cross-Service Conventions

| Concern | Convention |
|---------|-----------|
| **Time** | UTC everywhere. `int64` Unix milliseconds in transport. Local time only at the UI display layer. |
| **Money** | Never floating point. Go: `decimal.Decimal` (shopspring). Python: `Decimal`. Transported as strings (`"0.00012345"`). |
| **IDs** | ULID, lowercase, generated by the producing service. |
| **Logging** | Structured JSON. Required keys: `service`, `mode`, `symbol`, `request_id`. |
| **Errors** | Never swallowed. Returned up the call stack or logged at `error` with full context. |
| **Config** | YAML files validated on startup. Environment variables override file values. No hardcoded symbols, thresholds, or API keys. |

---

## Important Things to Know

1. **Paper mode is the safe default.** The system starts in paper mode with testnet connections. You cannot accidentally trade real money without passing three independent gates.

2. **Risk engine is non-negotiable.** Every order in every mode passes through the same risk checks. There is no bypass. If the risk engine rejects an order, it creates an alert and the order is dropped.

3. **The kill switch is immediate.** `POST /api/bot/kill` cancels all open orders, flattens all positions, and halts the bot. Use it if something goes wrong in live trading.

4. **AI is optional.** The system works with rule-based strategies (`ma_cross`, `rsi`) alone. AI training, inference, and the Python service are only needed if you want ML-driven signals.

5. **All market data flows through the Go backend.** The AI service never calls Binance. It requests bar data from the backend, which owns the Binance connection.

6. **Decimal precision matters.** Prices and quantities are never stored or computed as floating-point numbers. The system uses arbitrary-precision decimals throughout.

7. **Backtest before paper, paper before live.** The recommended workflow is: backtest a strategy on historical data, then run it in paper mode with real-time prices, and only then consider live trading after verifying performance.

8. **Database migrations must run in order.** The eight SQL files in `apps/backend/migrations/` must be applied sequentially (0001 through 0008) before the backend starts.

9. **WebSocket reconnection is automatic.** If the Binance WebSocket disconnects, the system reconnects with exponential backoff (up to 30 seconds). A `binance_disconnect` alert is created.

10. **Model promotion is explicit.** Training a new AI model does not automatically make it active. You must promote it via the UI or API. The previous active model remains until replaced.

---
