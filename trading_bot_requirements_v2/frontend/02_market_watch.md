# Frontend - Market Watch

## Purpose
Page for displaying price charts and market data for the selected symbol.

## Functional Requirements
1. Select a symbol, such as BTCUSDT or ETHUSDT
2. Select a timeframe, such as 1m, 5m, 15m, 1h, or 4h
3. Display a candlestick chart
4. Display volume
5. Display indicator overlays, such as EMA, RSI, and MACD
6. Display AI signal markers on the chart
7. Display the latest price in real time

## API / Events Needed
- `GET /api/market/symbols`
- `GET /api/market/candles`
- `WS /ws/market`

## Data Display / Data Stored
- Candles OHLCV
- Indicators
- Latest price
- AI signal markers

## Acceptance Criteria
- [ ] The chart changes based on the selected symbol/timeframe
- [ ] The latest price updates from WebSocket
- [ ] Indicators display correctly based on backend data

## Priority
MVP Core
