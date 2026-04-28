# Backend - Order Manager

## Purpose
จัดการ order จริงและ order จำลองผ่าน interface เดียว

## Functional Requirements
1. สร้าง order request
2. รองรับ market/limit order
3. ติดตาม order status
4. แยก paper/live execution
5. บันทึก order log
6. จัดการ retry เฉพาะกรณีปลอดภัย

## API / Events Needed
- `POST /orders`
- `GET /orders`
- `Internal execution adapter`

## Data Display / Data Stored
- Order request
- Order status
- Fill details
- Fee

## Acceptance Criteria
- [ ] order lifecycle ถูกต้อง
- [ ] paper/live แยกชัดเจน
- [ ] ไม่ส่ง order ซ้ำโดยไม่ตั้งใจ

## Priority
MVP Core
