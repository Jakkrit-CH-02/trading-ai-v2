# Frontend - Alert Center

## Purpose
หน้ารวม notification, error, warning และ trade event

## Functional Requirements
1. แสดง alert list
2. แยก severity: info, warning, critical
3. filter ตาม type/date
4. mark as read
5. แสดงรายละเอียด error

## API / Events Needed
- `GET /api/alerts`
- `PATCH /api/alerts/{id}/read`
- `WS /ws/alerts`

## Data Display / Data Stored
- Alert message
- Severity
- Timestamp
- Related bot/trade/system

## Acceptance Criteria
- [ ] รับ alert real-time ได้
- [ ] แสดง critical alert ชัดเจน
- [ ] mark as read ได้

## Priority
MVP Core
