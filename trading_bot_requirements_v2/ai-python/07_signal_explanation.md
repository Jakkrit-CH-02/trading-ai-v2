# AI Service - Signal Explanation

## Purpose
อธิบายเหตุผลของ signal เพื่อช่วย debug และแสดงบน dashboard

## Functional Requirements
1. สร้าง explanation จาก feature importance/rules
2. แสดง top factors ที่มีผลต่อ signal
3. บันทึก explanation พร้อม trade log
4. รองรับ explain แบบง่ายใน MVP

## API / Events Needed
- `Included in /ai/inference response`

## Data Display / Data Stored
- Signal reason
- Top features
- Confidence explanation

## Acceptance Criteria
- [ ] ทุก signal มี reason ขั้นพื้นฐาน
- [ ] frontend แสดงเหตุผลได้
- [ ] ช่วย debug model ได้

## Priority
MVP Core
