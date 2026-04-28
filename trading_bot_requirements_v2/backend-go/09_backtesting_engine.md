# Backend - Backtesting Engine

## Purpose
Test strategies against historical data.

## Functional Requirements
1. Select symbol/timeframe/date range
2. Run strategy on historical candles
3. Simulate orders, fees, and slippage
4. Calculate metrics
5. Store backtest results

## API / Events Needed
- `POST /backtests/run`
- `GET /backtests/{id}`

## Data Display / Data Stored
- Backtest config
- Trades
- Metrics
- Equity curve

## Acceptance Criteria
- [ ] Backtests can be run repeatedly
- [ ] Results are reproducible
- [ ] Core metrics are complete

## Priority
MVP Core
