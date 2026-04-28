# Backend - Risk Engine

## Purpose
Validate risk before sending orders.

## Functional Requirements
1. Calculate position size
2. Check max daily loss
3. Check max drawdown
4. Check max open positions
5. Check leverage limits
6. Block orders that violate risk rules

## API / Events Needed
- `GET /risk/status`
- `Internal validateOrder`

## Data Display / Data Stored
- Risk limits
- Exposure
- Drawdown
- Validation result

## Acceptance Criteria
- [ ] Every order must pass through the risk engine
- [ ] Orders are rejected when limits are exceeded
- [ ] Rejection reasons are stored

## Priority
MVP Core
