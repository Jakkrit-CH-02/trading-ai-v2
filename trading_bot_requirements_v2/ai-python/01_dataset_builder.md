# AI Service - Dataset Builder

## Purpose
เตรียม dataset จากข้อมูลตลาดย้อนหลังเพื่อใช้ train AI

## Functional Requirements
1. โหลด candles จาก database
2. เลือก symbol/timeframe/date range
3. สร้าง label เช่น next candle direction หรือ future return
4. split train/validation/test
5. บันทึก dataset metadata

## API / Events Needed
- `POST /ai/datasets/build`
- `GET /ai/datasets`

## Data Display / Data Stored
- OHLCV
- Labels
- Dataset metadata

## Acceptance Criteria
- [ ] สร้าง dataset ซ้ำได้
- [ ] ไม่มี data leakage พื้นฐาน
- [ ] metadata ครบ

## Priority
MVP Core
