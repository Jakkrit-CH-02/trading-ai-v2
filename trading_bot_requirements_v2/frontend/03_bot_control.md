# Frontend - Bot Control

## Purpose
หน้าควบคุมการทำงานของ bot

## Functional Requirements
1. Start, Stop, Pause bot
2. เลือก mode: backtest, paper, live
3. เลือก strategy
4. เลือก symbol และ timeframe
5. ตั้ง risk per trade เบื้องต้น
6. แสดง confirmation ก่อนเปิด live trading
7. แสดงสถานะ runtime ล่าสุด

## API / Events Needed
- `POST /api/bot/start`
- `POST /api/bot/stop`
- `POST /api/bot/pause`
- `GET /api/bot/status`
- `GET /api/strategies`

## Data Display / Data Stored
- Bot mode
- Selected strategy
- Runtime state
- Risk config

## Acceptance Criteria
- [ ] สั่ง start/stop ได้จากหน้า UI
- [ ] ไม่สามารถเปิด live trading โดยไม่ confirm
- [ ] แสดง error message เมื่อ backend ปฏิเสธคำสั่ง

## Priority
MVP Core
