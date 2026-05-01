# Binance AI Trading Bot — Feature Files Index

## Folder Structure

```text
binance_ai_trading_bot_features_by_service/
├── frontend/
├── backend/
├── ai-service/
└── docs/
```

## Phase Summary

```text
Phase 0: Project Foundation
Phase 1: Market Data + Dashboard MVP
Phase 2: AI Dataset + Feature Engineering
Phase 3: AI Training + Inference
Phase 4: Strategy + Risk + Paper Trading
Phase 5: Backtesting + Evaluation
Phase 6: Live Trading Safety
Phase 7: Optimization + Automation
```

## Recommended Build Order

### Sprint 1 — Foundation
1. Project structure
2. Docker compose
3. Backend Fiber skeleton
4. AI service skeleton
5. Frontend Vite skeleton
6. Shared API contract
7. Health checks

### Sprint 2 — Market Data
1. Backend: Binance Connector
2. Backend: Market Data Service
3. Frontend: Market Watch
4. Frontend: Dashboard

### Sprint 3 — AI Data
1. AI Service: Dataset Builder
2. AI Service: Feature Engineering
3. Frontend: AI Training Page basic form

### Sprint 4 — AI Model
1. AI Service: Training Pipeline
2. AI Service: Model Registry
3. AI Service: Inference API
4. AI Service: Signal Explanation
5. Frontend: AI Training Page complete

### Sprint 5 — Paper Trading Core
1. Backend: Strategy Engine
2. Backend: Risk Engine
3. Backend: Order Manager
4. Backend: Paper Trading Engine
5. Backend: Trade Log Service
6. Backend: Bot Runtime Manager
7. Frontend: Bot Control
8. Frontend: Paper Trading
9. Frontend: Trade Logs
10. Frontend: Risk Monitor

### Sprint 6 — Backtesting
1. Backend: Backtest Engine
2. AI Service: Backtest AI Evaluation
3. Frontend: Backtesting Result

### Sprint 7 — Live Safety
1. Backend: Auth / User
2. Backend: Settings Service
3. Backend: Alert Service
4. Frontend: Settings
5. Frontend: Alert Center

## Must-Have Before Paper Trading

```text
- Binance Connector
- Market Data Service
- AI Inference API
- Strategy Engine
- Risk Engine
- Order Manager
- Paper Trading Engine
- Bot Control Page
- Paper Trading Page
- Trade Logs Page
```

## Must-Have Before Live Trading

```text
- Paper trading passed
- Backtesting passed
- AI evaluation passed
- Risk Engine ready
- Kill switch ready
- Audit log ready
- Alert Service ready
- Binance API permission checked
- Live Confirmation UI
- Admin Role Guard
- Model Registry separates paper/live models
- Trade logs can be reviewed historically
```
