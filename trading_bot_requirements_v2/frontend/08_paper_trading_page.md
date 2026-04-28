# Frontend - Paper Trading Page

## Purpose
หน้าแสดงผล portfolio จำลองก่อนใช้เงินจริง

## Functional Requirements
1. แสดง simulated balance
2. แสดง simulated open positions
3. แสดง paper trade history
4. แสดง performance report
5. reset portfolio ได้ตาม permission

## API / Events Needed
- `GET /api/paper/portfolio`
- `GET /api/paper/trades`
- `POST /api/paper/reset`

## Data Display / Data Stored
- Simulated balance
- Paper positions
- Paper PnL

## Acceptance Criteria
- [ ] จำลอง portfolio ได้โดยไม่ส่ง order จริง
- [ ] แยกข้อมูล paper กับ live ชัดเจน
- [ ] แสดง PnL ของ paper trading

## Priority
MVP Core
