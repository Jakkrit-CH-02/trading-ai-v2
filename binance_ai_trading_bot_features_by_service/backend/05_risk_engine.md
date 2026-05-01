# Backend Feature — Risk Engine

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core / Safety Critical

## Purpose
Validate risk before every order is submitted.

## Why This Phase
This must run before the Order Manager executes because it is the system's primary safety layer.

## Functional Requirements
1. Calculate position size
2. Check max daily loss
3. Check max drawdown
4. Check max open positions
5. Check leverage limits
6. Check minimum balance
7. Check symbol exposure
8. Check AI confidence threshold
9. Block orders that violate risk rules
10. Record reject reasons
11. Support the kill switch

## API / Events
```http
GET  /api/risk/status
POST /api/risk/kill-switch
WS   /ws/risk
```

```text
Internal validateOrder(signal, portfolio, riskConfig)
```

## Data Stored
- Risk limits
- Exposure
- Drawdown
- Validation result
- Reject reason
- Kill switch state

## Dependencies
- Settings Service
- Order Manager
- Trade Log Service
- Paper Trading Engine
- Alert Service

## Deliverables
- Risk validation service
- Risk status API
- Kill switch state
- Reject reason logger
- Risk WebSocket event

## Acceptance Criteria
- Every order must pass through the Risk Engine
- Orders must be rejected when limits are exceeded
- Record reject reasons
- The kill switch must block new orders immediately
