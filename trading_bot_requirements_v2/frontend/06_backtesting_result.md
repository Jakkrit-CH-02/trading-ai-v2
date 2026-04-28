# Frontend - Backtesting Result

## Purpose
Page for displaying strategy test results from historical data.

## Functional Requirements
1. Select a backtest run to view results
2. Display the equity curve
3. Display win rate, profit factor, and max drawdown
4. Display the trade list for the backtest
5. Support comparing multiple strategies in the future

## API / Events Needed
- `POST /api/backtests/run`
- `GET /api/backtests/{id}`
- `GET /api/backtests`

## Data Display / Data Stored
- Backtest metrics
- Equity curve
- Trade history

## Acceptance Criteria
- [ ] Users can start a backtest from the UI
- [ ] Results are displayed after backend processing completes
- [ ] Core metrics are complete

## Priority
MVP Core
