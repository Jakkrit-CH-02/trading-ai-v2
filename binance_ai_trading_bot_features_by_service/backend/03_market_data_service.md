# Backend Feature — Market Data Service

## Phase
Phase 1 — Market Data + Dashboard MVP

## Priority
MVP Core

## Purpose
Serve market data to the frontend, Strategy Engine, and AI service.

## Why This Phase
This is required after the Binance Connector so market data can be stored and distributed to every part of the system.

## Functional Requirements
1. Read candles from the Binance Connector
2. Store candles in the database/cache
3. Read candles from the database/cache
4. Send realtime prices through WebSocket
5. Send realtime candle updates through WebSocket
6. Calculate basic indicators:
   - EMA
   - RSI
   - MACD
7. Provide an API for the latest market snapshot
8. Support multiple clients concurrently

## API / Events
```http
GET /api/market/symbols
GET /api/market/candles
GET /api/market/snapshot
WS  /ws/market
```

## Data Stored
- Candles OHLCV
- Latest price
- Indicators
- Market snapshots

## Dependencies
- Binance Connector
- Database
- Cache
- WebSocket Hub

## Deliverables
- Candle repository
- Market snapshot service
- Indicator calculator
- WebSocket broadcaster

## Acceptance Criteria
- The frontend can load charts quickly
- WebSocket streams data continuously
- Multiple clients are supported
- Candles are not duplicated by symbol/timeframe/open_time
