# Backend - Trade Log Service

## Purpose
Store and provide trade/order history.

## Functional Requirements
1. Store entry/exit data
2. Store PnL, fees, and reasons
3. Store AI confidence
4. Query/filter trade logs
5. Support export in the future

## API / Events Needed
- `GET /trades`
- `GET /orders`

## Data Display / Data Stored
- Trades
- Orders
- PnL
- Reason

## Acceptance Criteria
- [ ] Every trade has a log
- [ ] Users can search by symbol/mode/date
- [ ] Data matches the order manager

## Priority
MVP Core
