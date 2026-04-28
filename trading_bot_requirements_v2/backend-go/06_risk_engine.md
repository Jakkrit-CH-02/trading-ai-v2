# Backend - Risk Engine

## Purpose
ตรวจสอบความเสี่ยงก่อนส่ง order

## Functional Requirements
1. คำนวณ position size
2. ตรวจ max daily loss
3. ตรวจ max drawdown
4. ตรวจ max open positions
5. ตรวจ leverage limit
6. บล็อก order ที่ผิด risk rule

## API / Events Needed
- `GET /risk/status`
- `Internal validateOrder`

## Data Display / Data Stored
- Risk limits
- Exposure
- Drawdown
- Validation result

## Acceptance Criteria
- [ ] order ทุกตัวต้องผ่าน risk engine
- [ ] ถ้าเกิน limit ต้อง reject
- [ ] บันทึกเหตุผลการ reject

## Priority
MVP Core
