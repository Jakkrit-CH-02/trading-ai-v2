# Backend - Market Data Service

## Purpose
Provide market data to the frontend and other engines.

## Functional Requirements
1. Read candles from the database/cache
2. Send real-time price/candle data through WebSocket
3. Calculate basic indicators
4. Provide an API for the latest market snapshot

## API / Events Needed
- `GET /market/candles`
- `GET /market/snapshot`
- `WS /ws/market`

## Data Display / Data Stored
- Candles
- Latest price
- Indicators

## Acceptance Criteria
- [ ] The frontend can load charts quickly
- [ ] WebSocket sends data continuously
- [ ] Multiple clients are supported

## Priority
MVP Core
