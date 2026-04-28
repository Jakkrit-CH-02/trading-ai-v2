# Backend - Binance Connector

## Purpose
Connect to the Binance REST API and WebSocket.

## Functional Requirements
1. Connect to the REST API for account/order/exchange info
2. Connect to WebSocket for market streams
3. Support reconnection
4. Handle rate limits
5. Support testnet/mainnet configuration
6. Validate API key permissions

## API / Events Needed
- `Internal Binance client`

## Data Display / Data Stored
- Exchange info
- Account info
- Market stream
- Order response

## Acceptance Criteria
- [ ] Market data can be fetched
- [ ] Reconnects when the WebSocket disconnects
- [ ] Does not exceed rate limits unnecessarily

## Priority
MVP Core
