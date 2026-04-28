# Backend - Alert Service

## Purpose
Create and send alerts from important events.

## Functional Requirements
1. Create alerts from risk, trade, and system error events
2. Support severity levels
3. Send alerts to the frontend through WebSocket
4. Support Telegram/Discord in the future
5. Store alert history

## API / Events Needed
- `GET /alerts`
- `WS /ws/alerts`

## Data Display / Data Stored
- Alert
- Severity
- Read status

## Acceptance Criteria
- [ ] Critical alerts are sent to the frontend immediately
- [ ] History is stored
- [ ] Severity levels can be separated

## Priority
MVP Core
