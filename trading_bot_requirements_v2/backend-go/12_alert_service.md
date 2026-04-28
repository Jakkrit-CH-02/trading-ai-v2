# Backend - Alert Service

## Purpose
สร้างและส่ง alert จากเหตุการณ์สำคัญ

## Functional Requirements
1. สร้าง alert จาก risk, trade, system error
2. รองรับ severity
3. ส่ง WebSocket ไป frontend
4. รองรับ Telegram/Discord ในอนาคต
5. เก็บ alert history

## API / Events Needed
- `GET /alerts`
- `WS /ws/alerts`

## Data Display / Data Stored
- Alert
- Severity
- Read status

## Acceptance Criteria
- [ ] critical alert ส่งถึง frontend ทันที
- [ ] เก็บ history
- [ ] แยก severity ได้

## Priority
MVP Core
