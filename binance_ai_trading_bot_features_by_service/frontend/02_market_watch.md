# Frontend Feature — Market Watch

## Phase
Phase 1 — Market Data + Dashboard MVP

## Priority
MVP Core

## Purpose
A page that displays price charts and market data for the selected symbol.

## Why This Phase
This should be built after the Backend Market Data Service because it requires candles, indicators, and realtime market streams.

## Functional Requirements
1. Select symbols such as BTCUSDT or ETHUSDT
2. Select timeframes such as 1m, 5m, 15m, 1h, 4h, 1d
3. Display a candlestick chart
4. Display volume
5. Display indicator overlays:
   - EMA
   - RSI
   - MACD
   - Bollinger Bands in the future
6. Display AI signal markers on the chart in Phase 3+
7. Display the latest price in realtime
8. Display market snapshots:
   - 24h change
   - 24h volume
   - high/low
   - spread

## UI Requirements
- Use MUI `Box`, `Card`, `Stack`, `Select`, `Chip`
- Use only `sx` for styling
- The chart area is the main page area
- Include a top filter for symbol/timeframe
- Include loading, empty, and error states

## API / Events
```http
GET /api/market/symbols
GET /api/market/candles?symbol=BTCUSDT&timeframe=5m
GET /api/market/snapshot?symbol=BTCUSDT
WS  /ws/market
```

## Data Display
- Candles OHLCV
- Indicators
- Latest price
- Volume
- AI signal markers

## Dependencies
- Backend Binance Connector
- Backend Market Data Service
- AI Inference API for signal markers in Phase 3+

## Deliverables
- `MarketWatchPage`
- `SymbolSelector`
- `TimeframeSelector`
- `CandlestickChart`
- `IndicatorPanel`
- `MarketSnapshotCard`

## Acceptance Criteria
- Changing the symbol updates the chart correctly
- Changing the timeframe reloads candles correctly
- Latest price updates through WebSocket
- Indicators render correctly based on backend data
