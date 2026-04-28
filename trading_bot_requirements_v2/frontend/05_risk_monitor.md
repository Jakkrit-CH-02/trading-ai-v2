# Frontend - Risk Monitor

## Purpose
หน้าแสดงและติดตามความเสี่ยงของระบบ

## Functional Requirements
1. แสดง max daily loss
2. แสดง current drawdown
3. แสดง risk per trade
4. แสดง leverage และ position size
5. แสดงจำนวน open positions
6. แจ้งเตือนเมื่อ risk ใกล้ถึง limit
7. มีปุ่ม emergency stop/kill switch ใน phase live

## API / Events Needed
- `GET /api/risk/status`
- `POST /api/risk/kill-switch`
- `WS /ws/risk`

## Data Display / Data Stored
- Drawdown
- Daily loss
- Position exposure
- Risk limits

## Acceptance Criteria
- [ ] เห็น risk status ชัดเจน
- [ ] แสดง warning เมื่อเกิน threshold
- [ ] risk value ตรงกับ backend

## Priority
MVP Core
