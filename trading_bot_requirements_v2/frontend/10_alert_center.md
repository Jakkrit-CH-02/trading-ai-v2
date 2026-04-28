# Frontend - Alert Center

## Purpose
Page for collecting notifications, errors, warnings, and trade events.

## Functional Requirements
1. Display the alert list
2. Separate severity levels: info, warning, critical
3. Filter by type/date
4. Mark alerts as read
5. Display error details

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
- [ ] Real-time alerts can be received
- [ ] Critical alerts are clearly displayed
- [ ] Alerts can be marked as read

## Priority
MVP Core
