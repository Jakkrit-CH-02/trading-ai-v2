# Frontend Feature — Alert Center

## Phase
Phase 6 — Live Trading Safety

## Priority
MVP Core / Live Required

## Purpose
A consolidated page for notifications, errors, warnings, and trade events.

## Why This Phase
This should be built before live trading because live mode needs realtime notifications for critical errors, risk events, and orders.

## Functional Requirements
1. Display the alert list
2. Separate severities:
   - info
   - warning
   - critical
3. Filter by type
4. Filter by date
5. Mark as read
6. Display error details
7. Receive realtime alerts through WebSocket
8. Display a critical alert banner

## UI Requirements
- Critical alerts must be the most prominent
- The alert list must be easy to read
- Include unread badges
- Include a filter bar

## API / Events
```http
GET   /api/alerts
PATCH /api/alerts/:id/read
WS    /ws/alerts
```

## Data Display
- Alert message
- Severity
- Timestamp
- Related bot/trade/order/system
- Read status

## Dependencies
- Backend Alert Service
- Backend Risk Engine
- Backend Order Manager
- Backend Bot Runtime Manager

## Deliverables
- `AlertCenterPage`
- `AlertList`
- `AlertFilterBar`
- `CriticalAlertBanner`
- `AlertDetailDrawer`

## Acceptance Criteria
- Realtime alerts can be received
- Critical alerts are displayed clearly
- Alerts can be marked as read
- Alert history persists after refresh
