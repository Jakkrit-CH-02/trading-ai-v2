# Backend - Data Collector

## Purpose
ดึงและบันทึกข้อมูลตลาดจาก Binance

## Functional Requirements
1. ดึง historical candles
2. subscribe realtime candles
3. บันทึก OHLCV ลง database
4. ตรวจ duplicate/missing candles
5. รองรับหลาย symbol/timeframe

## API / Events Needed
- `POST /data/download`
- `GET /data/status`

## Data Display / Data Stored
- OHLCV
- Symbol
- Timeframe
- Download job

## Acceptance Criteria
- [ ] มีข้อมูลย้อนหลังพร้อมใช้ backtest/train
- [ ] ข้อมูลไม่ซ้ำ
- [ ] ตรวจ missing candle ได้

## Priority
MVP Core
