# Frontend - Trade Logs

## Purpose
หน้าดูประวัติ order และ trade ทั้งหมด

## Functional Requirements
1. แสดง trade list แบบ table
2. filter ตาม symbol, strategy, mode, date
3. แสดง entry, exit, quantity, fee, PnL
4. แสดงเหตุผลการเข้า trade
5. แสดง AI confidence ตอนเข้า trade
6. export CSV ได้ในอนาคต

## API / Events Needed
- `GET /api/trades`
- `GET /api/orders`

## Data Display / Data Stored
- Trade ID
- Order ID
- Entry/exit price
- PnL
- Reason
- AI confidence

## Acceptance Criteria
- [ ] ค้นหาและ filter trade ได้
- [ ] แสดงข้อมูล PnL ถูกต้อง
- [ ] เปิดดูรายละเอียด trade รายตัวได้

## Priority
MVP Core
