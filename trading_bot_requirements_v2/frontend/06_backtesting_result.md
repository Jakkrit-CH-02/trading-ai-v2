# Frontend - Backtesting Result

## Purpose
หน้าแสดงผลการทดสอบ strategy จากข้อมูลย้อนหลัง

## Functional Requirements
1. เลือก backtest run เพื่อดูผล
2. แสดง equity curve
3. แสดง win rate, profit factor, max drawdown
4. แสดง trade list ของ backtest
5. เปรียบเทียบหลาย strategy ได้ในอนาคต

## API / Events Needed
- `POST /api/backtests/run`
- `GET /api/backtests/{id}`
- `GET /api/backtests`

## Data Display / Data Stored
- Backtest metrics
- Equity curve
- Trade history

## Acceptance Criteria
- [ ] เริ่ม backtest ได้จาก UI
- [ ] แสดงผลหลัง backend ประมวลผลเสร็จ
- [ ] metric หลักครบ

## Priority
MVP Core
