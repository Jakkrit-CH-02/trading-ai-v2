# Backend Feature — Backtest Engine

## Phase
Phase 5 — Backtesting + Evaluation

## Priority
MVP Core / Phase 2 Core

## Purpose
Simulate strategies against historical data before real usage.

## Why This Phase
This should be built after Strategy, Risk, and Paper Trading because backtesting should reuse the same logic for historical simulation.

## Functional Requirements
1. Receive backtest config
2. Load historical candles
3. Call the Strategy Engine
4. Use Risk Engine rules
5. Simulate order fills
6. Calculate fees/slippage
7. Calculate PnL
8. Create the equity curve
9. Calculate metrics:
   - win rate
   - profit factor
   - max drawdown
   - total return
10. Store backtest results

## API / Events
```http
POST /api/backtests/run
GET  /api/backtests
GET  /api/backtests/:id
```

## Data Stored
- Backtest config
- Backtest metrics
- Equity curve
- Backtest trades
- Strategy/model version

## Dependencies
- Market Data Service
- Strategy Engine
- Risk Engine
- Order fill simulator
- AI Inference API or batch prediction

## Deliverables
- Backtest runner
- Metrics calculator
- Equity curve generator
- Backtest result repository

## Acceptance Criteria
- Backtests can be run
- Core metrics are complete
- Trade lists can be reviewed
- Results are stored and can be opened later
