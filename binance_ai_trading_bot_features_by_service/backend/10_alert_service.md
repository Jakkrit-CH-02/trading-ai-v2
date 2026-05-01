# Backend Feature — Alert Service

## Phase
Phase 6 — Live Trading Safety

## Priority
MVP Core / Live Required

## Purpose
Create and send alerts for important events.

## Why This Phase
This must be ready before live trading to notify users about risk, order, system error, and connection issues in realtime.

## Functional Requirements
1. Create alerts from risk events
2. Create alerts from trade/order events
3. Create alerts from system errors
4. Create alerts when Binance disconnects
5. Create alerts when the AI service is unavailable
6. Support severities:
   - info
   - warning
   - critical
7. Send WebSocket events to the frontend
8. Store alert history
9. Support Telegram/Discord in the future
10. Mark as read

## API / Events
```http
GET   /api/alerts
PATCH /api/alerts/:id/read
WS    /ws/alerts
```

## Data Stored
- Alert message
- Severity
- Type
- Related entity
- Read status
- Created at

## Dependencies
- Risk Engine
- Order Manager
- Bot Runtime Manager
- Binance Connector
- AI Service Health Check

## Deliverables
- Alert repository
- Alert event bus
- WebSocket alert broadcaster
- Mark-as-read API
- Critical alert handling

## Acceptance Criteria
- Critical alerts are sent to the frontend immediately
- History is stored
- Severity can be separated
- Alerts can be linked to related bot/trade/order/system entities
