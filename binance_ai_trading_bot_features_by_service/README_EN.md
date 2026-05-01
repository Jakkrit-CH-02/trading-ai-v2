# README — Binance AI Trading Bot Feature Phase Map

This document explains **which requirement file belongs to which development phase**, how each feature should be built, and the recommended build order across:

```text
frontend/
backend/
ai-service/
```

---

## Folder Structure

```text
binance_ai_trading_bot_features_by_service/
├── frontend/
├── backend/
├── ai-service/
└── docs/
```

---

# Phase 0 — Project Foundation

## Purpose

Prepare the base project structure, service skeletons, Docker setup, shared API contracts, environment configuration, and health checks before building product features.

## Files

There are no dedicated feature files for Phase 0 in this package because Phase 0 is a foundation layer for the whole system.

## Recommended Files To Create Later

```text
docs/phase_0_project_foundation.md
docs/shared_api_contract.md
docs/docker_setup.md
docs/environment_config.md
```

## Recommended Build Order

1. Create the monorepo or project structure.
2. Create the frontend React Vite skeleton.
3. Create the backend Golang Fiber skeleton.
4. Create the Python AI service skeleton.
5. Create Docker Compose.
6. Create health check endpoints.
7. Define shared API contracts.

## Why This Phase Comes First

All later features depend on a stable folder structure, consistent API contracts, and working service communication.

---

# Phase 1 — Market Data + Dashboard MVP

## Purpose

Connect to Binance, collect market data, expose market APIs/WebSocket streams, and display the first usable dashboard and market chart UI.

## Backend Files

```text
backend/02_binance_connector.md
backend/03_market_data_service.md
```

## Frontend Files

```text
frontend/01_dashboard.md
frontend/02_market_watch.md
```

## AI Service Files

No AI service feature is required in this phase.

## Recommended Build Order

1. `backend/02_binance_connector.md`
2. `backend/03_market_data_service.md`
3. `frontend/02_market_watch.md`
4. `frontend/01_dashboard.md`

## Why This Phase Comes First

The AI service, strategy engine, backtesting, and paper trading all depend on reliable market data. Binance connectivity and market data display should be completed before AI-related development.

## Expected Outcome

After this phase, the system should be able to:

- Connect to Binance REST/WebSocket.
- Fetch symbols and candle data.
- Stream live market data.
- Display candlestick charts.
- Display basic dashboard health/status.

---

# Phase 2 — AI Dataset + Feature Engineering

## Purpose

Prepare historical market datasets, generate labels, calculate technical indicators, create feature matrices, and define a consistent feature schema for training and inference.

## AI Service Files

```text
ai-service/01_dataset_builder.md
ai-service/02_feature_engineering.md
```

## Backend Files Used As Dependency

```text
backend/03_market_data_service.md
```

## Frontend Files Used Later

```text
frontend/06_ai_training_page.md
```

## Recommended Build Order

1. `ai-service/01_dataset_builder.md`
2. `ai-service/02_feature_engineering.md`

## Why This Phase Comes After Phase 1

The dataset and features are built from historical OHLCV candles provided by the Market Data Service.

## Expected Outcome

After this phase, the AI service should be able to:

- Build historical datasets.
- Generate labels for supervised learning.
- Calculate indicators such as RSI, MACD, EMA, ATR, and Bollinger Bands.
- Save feature schemas.
- Ensure training and inference use the same feature format.

---

# Phase 3 — AI Training + Inference

## Purpose

Train models, manage model versions, activate models, expose inference APIs, and return explainable trading signals.

## AI Service Files

```text
ai-service/03_training_pipeline.md
ai-service/04_model_registry.md
ai-service/05_inference_api.md
ai-service/07_signal_explanation.md
```

## Frontend Files

```text
frontend/06_ai_training_page.md
```

## Backend Notes

There is no dedicated backend feature file in this phase, but the backend should provide an API proxy or internal client to communicate with the AI service.

## Recommended Build Order

1. `ai-service/03_training_pipeline.md`
2. `ai-service/04_model_registry.md`
3. `ai-service/05_inference_api.md`
4. `ai-service/07_signal_explanation.md`
5. `frontend/06_ai_training_page.md`

## Why This Phase Comes After Phase 2

Training and inference require datasets, feature engineering logic, and a stable feature schema.

## Expected Outcome

After this phase, the system should be able to:

- Train a model from selected datasets.
- Save model artifacts.
- Track model versions.
- Activate a model for paper mode.
- Run inference and return `BUY`, `SELL`, or `HOLD`.
- Return confidence, risk score, model version, and signal explanation.

---

# Phase 4 — Strategy + Risk + Paper Trading

## Purpose

Enable the bot to make trading decisions and execute simulated trades without using real money.

## Backend Files

```text
backend/04_strategy_engine.md
backend/05_risk_engine.md
backend/06_order_manager.md
backend/07_paper_trading_engine.md
backend/11_trade_log_service.md
backend/12_bot_runtime_manager.md
```

## Frontend Files

```text
frontend/03_bot_control.md
frontend/04_trade_logs.md
frontend/07_paper_trading_page.md
frontend/08_risk_monitor.md
```

## AI Service Files Used As Dependency

```text
ai-service/05_inference_api.md
ai-service/07_signal_explanation.md
```

## Recommended Build Order

1. `backend/04_strategy_engine.md`
2. `backend/05_risk_engine.md`
3. `backend/06_order_manager.md`
4. `backend/07_paper_trading_engine.md`
5. `backend/11_trade_log_service.md`
6. `backend/12_bot_runtime_manager.md`
7. `frontend/03_bot_control.md`
8. `frontend/07_paper_trading_page.md`
9. `frontend/04_trade_logs.md`
10. `frontend/08_risk_monitor.md`

## Why This Phase Comes After Phase 3

The Strategy Engine depends on AI inference results. The system should already be able to produce AI signals before building the trading decision and execution flow.

## Expected Outcome

After this phase, the system should be able to:

- Start, stop, and pause the bot.
- Generate a final strategy signal.
- Validate all orders through the Risk Engine.
- Execute paper trades only.
- Track simulated positions and PnL.
- Store trade logs with reasons and AI confidence.
- Display risk status and paper portfolio in the frontend.

---

# Phase 5 — Backtesting + Evaluation

## Purpose

Test strategies and AI models against historical data before promoting them to paper or live trading.

## Backend Files

```text
backend/08_backtest_engine.md
```

## AI Service Files

```text
ai-service/06_backtest_ai_evaluation.md
```

## Frontend Files

```text
frontend/05_backtesting_result.md
```

## Recommended Build Order

1. `backend/08_backtest_engine.md`
2. `ai-service/06_backtest_ai_evaluation.md`
3. `frontend/05_backtesting_result.md`

## Why This Phase Comes After Phase 4

Backtesting should reuse or closely mirror the real strategy, risk, and order simulation logic from the paper trading system.

## Expected Outcome

After this phase, the system should be able to:

- Run backtests on historical candles.
- Calculate win rate, profit factor, max drawdown, and total return.
- Generate an equity curve.
- Compare AI model performance with baseline strategies.
- Block weak models from being promoted.

---

# Phase 6 — Live Trading Safety

## Purpose

Add the safety, security, audit, alerting, and settings layers required before enabling real Binance order execution.

## Backend Files

```text
backend/01_auth_user.md
backend/09_settings_service.md
backend/10_alert_service.md
```

## Frontend Files

```text
frontend/09_settings.md
frontend/10_alert_center.md
```

## AI Service Files Used As Dependency

```text
ai-service/04_model_registry.md
ai-service/06_backtest_ai_evaluation.md
```

## Recommended Build Order

1. `backend/01_auth_user.md`
2. `backend/09_settings_service.md`
3. `backend/10_alert_service.md`
4. `frontend/09_settings.md`
5. `frontend/10_alert_center.md`

## Why This Phase Comes Before Live Trading

Live trading should never be enabled without authentication, role-based access control, audit logs, API key validation, alerts, kill switch behavior, and model evaluation guards.

## Expected Outcome

After this phase, the system should be ready to safely prepare for live trading, but live execution should still only be enabled after full testing.

---

# Phase 7 — Optimization + Automation

## Purpose

Add advanced capabilities after the MVP, paper trading, backtesting, and safety layers are stable.

## Files

No dedicated feature files for Phase 7 are included in this package yet.

## Recommended Files To Create Later

```text
backend/13_notification_integration.md
backend/14_multi_symbol_portfolio.md
backend/15_advanced_strategy_management.md
ai-service/08_auto_retraining.md
frontend/11_performance_analytics.md
frontend/12_strategy_management.md
```

## Possible Features

- Multi-symbol trading
- Multi-strategy management
- Telegram/Discord notification
- Auto retraining
- Model drift detection
- Performance analytics
- Exportable reports

---

# Complete File Map

## Frontend

| File | Phase | Feature |
|---|---:|---|
| `frontend/01_dashboard.md` | Phase 1 | Dashboard |
| `frontend/02_market_watch.md` | Phase 1 | Market Watch |
| `frontend/03_bot_control.md` | Phase 4 | Bot Control |
| `frontend/04_trade_logs.md` | Phase 4 | Trade Logs |
| `frontend/05_backtesting_result.md` | Phase 5 | Backtesting Result |
| `frontend/06_ai_training_page.md` | Phase 3 | AI Training Page |
| `frontend/07_paper_trading_page.md` | Phase 4 | Paper Trading Page |
| `frontend/08_risk_monitor.md` | Phase 4 | Risk Monitor |
| `frontend/09_settings.md` | Phase 6 | Settings |
| `frontend/10_alert_center.md` | Phase 6 | Alert Center |

## Backend

| File | Phase | Feature |
|---|---:|---|
| `backend/01_auth_user.md` | Phase 6 | Auth / User |
| `backend/02_binance_connector.md` | Phase 1 | Binance Connector |
| `backend/03_market_data_service.md` | Phase 1 | Market Data Service |
| `backend/04_strategy_engine.md` | Phase 4 | Strategy Engine |
| `backend/05_risk_engine.md` | Phase 4 | Risk Engine |
| `backend/06_order_manager.md` | Phase 4 | Order Manager |
| `backend/07_paper_trading_engine.md` | Phase 4 | Paper Trading Engine |
| `backend/08_backtest_engine.md` | Phase 5 | Backtest Engine |
| `backend/09_settings_service.md` | Phase 6 | Settings Service |
| `backend/10_alert_service.md` | Phase 6 | Alert Service |
| `backend/11_trade_log_service.md` | Phase 4 | Trade Log Service |
| `backend/12_bot_runtime_manager.md` | Phase 4 | Bot Runtime Manager |

## AI Service

| File | Phase | Feature |
|---|---:|---|
| `ai-service/01_dataset_builder.md` | Phase 2 | Dataset Builder |
| `ai-service/02_feature_engineering.md` | Phase 2 | Feature Engineering |
| `ai-service/03_training_pipeline.md` | Phase 3 | Training Pipeline |
| `ai-service/04_model_registry.md` | Phase 3 | Model Registry |
| `ai-service/05_inference_api.md` | Phase 3 | Inference API |
| `ai-service/06_backtest_ai_evaluation.md` | Phase 5 | Backtest AI Evaluation |
| `ai-service/07_signal_explanation.md` | Phase 3 | Signal Explanation |

---

# Dependency Map

## Phase 1 Dependency

```text
Binance Connector
  → Market Data Service
    → Market Watch
    → Dashboard
```

## Phase 2 Dependency

```text
Market Data Service
  → Dataset Builder
    → Feature Engineering
```

## Phase 3 Dependency

```text
Feature Engineering
  → Training Pipeline
    → Model Registry
      → Inference API
        → Signal Explanation
          → AI Training Page
```

## Phase 4 Dependency

```text
Inference API
  → Strategy Engine
    → Risk Engine
      → Order Manager
        → Paper Trading Engine
        → Trade Log Service
        → Bot Runtime Manager
```

## Phase 5 Dependency

```text
Strategy Engine + Risk Engine + Historical Data
  → Backtest Engine
    → Backtest AI Evaluation
      → Backtesting Result Page
```

## Phase 6 Dependency

```text
Auth/User + Settings Service + Alert Service
  → Live Trading Safety
  → Settings Page
  → Alert Center
```

---

# Short Build Checklist

## Required Before Paper Trading

```text
[ ] backend/02_binance_connector.md
[ ] backend/03_market_data_service.md
[ ] ai-service/01_dataset_builder.md
[ ] ai-service/02_feature_engineering.md
[ ] ai-service/03_training_pipeline.md
[ ] ai-service/04_model_registry.md
[ ] ai-service/05_inference_api.md
[ ] backend/04_strategy_engine.md
[ ] backend/05_risk_engine.md
[ ] backend/06_order_manager.md
[ ] backend/07_paper_trading_engine.md
[ ] backend/11_trade_log_service.md
[ ] backend/12_bot_runtime_manager.md
[ ] frontend/03_bot_control.md
[ ] frontend/07_paper_trading_page.md
[ ] frontend/04_trade_logs.md
```

## Required Before Live Trading

```text
[ ] Paper trading tested
[ ] Backtesting passed
[ ] AI evaluation passed
[ ] backend/01_auth_user.md
[ ] backend/09_settings_service.md
[ ] backend/10_alert_service.md
[ ] frontend/09_settings.md
[ ] frontend/10_alert_center.md
[ ] Kill switch ready
[ ] Audit log ready
[ ] Binance API permission checked
[ ] Model Registry separates paper/live models
```

---

# Recommended MVP Delivery Milestones

## Milestone 1 — Market Visibility

Deliver:

```text
backend/02_binance_connector.md
backend/03_market_data_service.md
frontend/02_market_watch.md
frontend/01_dashboard.md
```

Goal:

```text
The user can see Binance market data and system health in the UI.
```

---

## Milestone 2 — AI Signal Generation

Deliver:

```text
ai-service/01_dataset_builder.md
ai-service/02_feature_engineering.md
ai-service/03_training_pipeline.md
ai-service/04_model_registry.md
ai-service/05_inference_api.md
ai-service/07_signal_explanation.md
frontend/06_ai_training_page.md
```

Goal:

```text
The system can train a model and generate explainable BUY/SELL/HOLD signals.
```

---

## Milestone 3 — Paper Trading

Deliver:

```text
backend/04_strategy_engine.md
backend/05_risk_engine.md
backend/06_order_manager.md
backend/07_paper_trading_engine.md
backend/11_trade_log_service.md
backend/12_bot_runtime_manager.md
frontend/03_bot_control.md
frontend/07_paper_trading_page.md
frontend/04_trade_logs.md
frontend/08_risk_monitor.md
```

Goal:

```text
The bot can run in paper mode, simulate trades, calculate PnL, and record trade reasons.
```

---

## Milestone 4 — Backtesting

Deliver:

```text
backend/08_backtest_engine.md
ai-service/06_backtest_ai_evaluation.md
frontend/05_backtesting_result.md
```

Goal:

```text
The user can validate strategies and models against historical data before live trading.
```

---

## Milestone 5 — Live Safety Readiness

Deliver:

```text
backend/01_auth_user.md
backend/09_settings_service.md
backend/10_alert_service.md
frontend/09_settings.md
frontend/10_alert_center.md
```

Goal:

```text
The system has the required safety, security, alerting, and audit layers before live execution.
```
