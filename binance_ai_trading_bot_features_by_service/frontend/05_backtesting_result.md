# Frontend Feature — Backtesting Result

## Phase
Phase 5 — Backtesting + Evaluation

## Priority
MVP Core / Phase 2 Core

## Purpose
A page for displaying strategy or AI model backtest results from historical data.

## Why This Phase
This should be built after Strategy, Risk, and Paper Trading logic because backtests must simulate decisions/orders/risk close to the real system.

## Functional Requirements
1. Create a backtest run
2. Select a backtest result to review
3. Display the equity curve
4. Display win rate
5. Display profit factor
6. Display max drawdown
7. Display total return
8. Display the backtest trade list
9. Compare multiple strategies in the future

## UI Requirements
- Include metric cards at the top
- Equity curve is the main chart
- Trade table is placed below
- Display status while the backtest is running
- Include an empty state when there are no runs

## API / Events
```http
POST /api/backtests/run
GET  /api/backtests
GET  /api/backtests/:id
GET  /api/ai/evaluations/:id
```

## Data Display
- Backtest metrics
- Equity curve
- Trade history
- Strategy config
- Model version
- Evaluation result

## Dependencies
- Backend Backtest Engine
- Backend Strategy Engine
- Backend Risk Engine
- AI Backtest Evaluation

## Deliverables
- `BacktestingResultPage`
- `BacktestRunForm`
- `BacktestMetricsCards`
- `EquityCurveChart`
- `BacktestTradeTable`

## Acceptance Criteria
- Backtests can be started from the UI
- Results are displayed after backend processing completes
- Core metrics are complete
- The equity curve must correspond to the trade list
