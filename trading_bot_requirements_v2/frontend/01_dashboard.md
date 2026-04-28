# Frontend - Dashboard

## Purpose
หน้าแสดงภาพรวมการทำงานของ bot แบบ minimal เพื่อให้ผู้ใช้รู้สถานะระบบทันที

## Functional Requirements
1. แสดงสถานะ bot: running, paused, stopped, error
2. แสดง balance, equity, unrealized PnL, realized PnL
3. แสดง open positions ล่าสุด
4. แสดง AI signal ล่าสุดและ confidence
5. แสดง daily PnL และ drawdown
6. แสดง system health เช่น Binance connection, AI service, database

## API / Events Needed
- `GET /api/dashboard/summary`
- `WS /ws/dashboard`

## Data Display / Data Stored
- Bot status
- Balance/equity
- PnL
- Open positions
- Latest signal

## Acceptance Criteria
- [ ] เห็นภาพรวมระบบได้ในหน้าเดียว
- [ ] ข้อมูลสำคัญ refresh แบบ real-time หรือใกล้ real-time
- [ ] มี loading/error state

## Priority
MVP Core
