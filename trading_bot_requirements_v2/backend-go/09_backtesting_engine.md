# Backend - Backtesting Engine

## Purpose
ทดสอบ strategy กับข้อมูลย้อนหลัง

## Functional Requirements
1. เลือก symbol/timeframe/date range
2. run strategy บน candles ย้อนหลัง
3. จำลอง order, fee, slippage
4. คำนวณ metrics
5. บันทึก backtest result

## API / Events Needed
- `POST /backtests/run`
- `GET /backtests/{id}`

## Data Display / Data Stored
- Backtest config
- Trades
- Metrics
- Equity curve

## Acceptance Criteria
- [ ] run backtest ได้ซ้ำ
- [ ] ผลลัพธ์ reproducible
- [ ] metric หลักครบ

## Priority
MVP Core
