# Frontend Feature — Trade Logs

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core

## Purpose
A page for viewing all order and trade history, including trade-entry reasons and AI confidence.

## Why This Phase
This should be built after the Order Manager and Paper Trading Engine because order/trade data must exist before it can be displayed.

## Functional Requirements
1. Display the trade list as a table
2. Filter by symbol
3. Filter by strategy
4. Filter by mode: paper/live
5. Filter by date
6. Display entry price
7. Display exit price
8. Display quantity
9. Display fees
10. Display PnL
11. Display the trade-entry reason
12. Display AI confidence at trade entry
13. Allow viewing individual trade details
14. Export CSV in the future

## UI Requirements
- The table must be easy to read
- Include a filter bar at the top
- Use a drawer/modal for trade details
- Use different colors for positive/negative PnL
- Show clear paper/live badges

## API / Events
```http
GET /api/trades
GET /api/trades/:id
GET /api/orders
GET /api/orders/:id
```

## Data Display
- Trade ID
- Order ID
- Symbol
- Strategy
- Mode
- Entry/exit price
- Quantity
- Fee
- PnL
- Reason
- AI confidence

## Dependencies
- Backend Order Manager
- Backend Trade Log Service
- Backend Paper Trading Engine
- AI Signal Explanation

## Deliverables
- `TradeLogsPage`
- `TradeFilterBar`
- `TradeTable`
- `TradeDetailDrawer`

## Acceptance Criteria
- Trades can be searched and filtered
- PnL is displayed correctly
- Allow viewing individual trade details
- Every trade must have a reason and AI confidence when it comes from an AI strategy
