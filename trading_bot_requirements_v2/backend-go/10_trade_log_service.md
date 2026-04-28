# Backend - Trade Log Service

## Purpose
บันทึกและให้บริการประวัติ trade/order

## Functional Requirements
1. บันทึก entry/exit
2. บันทึก PnL, fee, reason
3. บันทึก AI confidence
4. query/filter trade logs
5. รองรับ export ในอนาคต

## API / Events Needed
- `GET /trades`
- `GET /orders`

## Data Display / Data Stored
- Trades
- Orders
- PnL
- Reason

## Acceptance Criteria
- [ ] ทุก trade มี log
- [ ] ค้นหาตาม symbol/mode/date ได้
- [ ] ข้อมูลตรงกับ order manager

## Priority
MVP Core
