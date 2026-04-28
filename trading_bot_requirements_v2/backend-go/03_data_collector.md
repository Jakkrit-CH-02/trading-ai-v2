# Backend - Data Collector

## Purpose
Fetch and store market data from Binance.

## Functional Requirements
1. Fetch historical candles
2. Subscribe to real-time candles
3. Store OHLCV in the database
4. Detect duplicate/missing candles
5. Support multiple symbols/timeframes

## API / Events Needed
- `POST /data/download`
- `GET /data/status`

## Data Display / Data Stored
- OHLCV
- Symbol
- Timeframe
- Download job

## Acceptance Criteria
- [ ] Historical data is available for backtesting/training
- [ ] Data is not duplicated
- [ ] Missing candles can be detected

## Priority
MVP Core
