# Frontend - Market Watch

## Purpose
หน้าแสดงกราฟราคาและข้อมูลตลาดสำหรับ symbol ที่เลือก

## Functional Requirements
1. เลือก symbol เช่น BTCUSDT, ETHUSDT
2. เลือก timeframe เช่น 1m, 5m, 15m, 1h, 4h
3. แสดง candlestick chart
4. แสดง volume
5. แสดง indicator overlay เช่น EMA, RSI, MACD
6. แสดง AI signal marker บนกราฟ
7. แสดงราคาล่าสุดแบบ real-time

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
- [ ] กราฟเปลี่ยนตาม symbol/timeframe ได้
- [ ] ราคาล่าสุดอัปเดตจาก WebSocket
- [ ] indicator แสดงถูกต้องตามข้อมูล backend

## Priority
MVP Core
