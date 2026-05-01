# Backend Feature — Trade Log Service

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core

## Purpose
Store signal, order, trade, reason, AI confidence, and PnL history for later review.

## Why This Phase
This should be built alongside Order Manager and Paper Trading so every decision is recorded from the beginning.

## Functional Requirements
1. Record every signal
2. Record every order request
3. Record every order status update
4. Record every fill
5. Record the trade lifecycle
6. Record AI confidence
7. Record signal explanations
8. Calculate PnL
9. Support filtering/search

## API / Events
```http
GET /api/trades
GET /api/trades/:id
GET /api/orders
GET /api/orders/:id
```

## Data Stored
- Signal
- Order
- Trade
- Position
- Reason
- AI confidence
- PnL
- Fee
- Mode paper/live

## Dependencies
- Strategy Engine
- Order Manager
- Paper Trading Engine
- AI Signal Explanation

## Deliverables
- Trade repository
- Order repository
- Signal repository
- PnL calculation utility
- Filter/search API

## Acceptance Criteria
- Full trade history can be viewed
- Every trade must have a reason
- PnL must be recalculable for verification
- Paper/live data must be clearly separated
