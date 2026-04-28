# Backend - Order Manager

## Purpose
Manage real and simulated orders through a single interface.

## Functional Requirements
1. Create order requests
2. Support market/limit orders
3. Track order status
4. Separate paper/live execution
5. Store order logs
6. Retry only when it is safe to do so

## API / Events Needed
- `POST /orders`
- `GET /orders`
- `Internal execution adapter`

## Data Display / Data Stored
- Order request
- Order status
- Fill details
- Fee

## Acceptance Criteria
- [ ] Order lifecycle is correct
- [ ] Paper/live execution is clearly separated
- [ ] Duplicate orders are not sent unintentionally

## Priority
MVP Core
