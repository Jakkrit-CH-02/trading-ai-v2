# Backend Feature — Binance Connector

## Phase
Phase 1 — Market Data + Dashboard MVP

## Priority
MVP Core

## Purpose
Connect to the Binance REST API and WebSocket.

## Why This Phase
This is the foundation for all market data and the main source for candles, tickers, exchange info, and future order execution.

## Functional Requirements
1. Connect to the Binance REST API
2. Connect to Binance WebSocket
3. Fetch exchange info
4. Fetch account info
5. Fetch historical candles
6. Subscribe to ticker streams
7. Subscribe to kline streams
8. Support reconnects
9. Handle rate limits
10. Support testnet/mainnet configuration
11. Validate API key permissions

## API / Internal
```http
GET  /api/binance/exchange-info
GET  /api/binance/symbols
POST /api/binance/key/test
```

## Internal Components
```text
BinanceClient
BinanceRestClient
BinanceWebSocketClient
RateLimitGuard
ReconnectManager
PermissionChecker
```

## Data Stored
- Exchange info
- Account info
- Market stream events
- Order responses in the live phase

## Dependencies
- Settings Service
- Secure Credential Store
- Logger

## Deliverables
- Binance REST client
- Binance WebSocket client
- reconnect logic
- rate limit guard
- permission checker

## Acceptance Criteria
- Market data can be fetched
- Reconnect when the WebSocket disconnects
- Avoid unnecessary rate-limit violations
- Testnet/mainnet configuration is clearly separated
