# Backend Feature — Order Manager

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core / Safety Critical

## Purpose
Manage real and simulated orders through the same interface.

## Why This Phase
This should be built after the Risk Engine because every order must pass risk validation before execution.

## Functional Requirements
1. Create order requests
2. Support market orders
3. Support limit orders
4. Track order status
5. Separate execution modes:
   - paper
   - live
6. Record order logs
7. Retry only when it is safe
8. Use idempotency keys to prevent duplicate orders
9. Route to the Paper Trading Engine or Binance Connector based on mode

## API / Events
```http
POST /api/orders
GET  /api/orders
GET  /api/orders/:id
```

## Data Stored
- Order request
- Order status
- Fill details
- Fee
- Idempotency key
- Execution mode

## Dependencies
- Risk Engine
- Paper Trading Engine
- Binance Connector
- Trade Log Service
- Alert Service

## Deliverables
- Order lifecycle manager
- Paper/live execution adapter
- Idempotency handling
- Order repository
- Retry guard

## Acceptance Criteria
- Order lifecycle is correct
- Paper/live modes are clearly separated
- Orders are not accidentally duplicated
- Live orders must pass through the Risk Engine
