# Backend - Paper Trading Engine

## Purpose
Simulate trading without using real money.

## Functional Requirements
1. Simulate balance
2. Simulate fill price from market data
3. Calculate fees/slippage
4. Manage open/closed positions
5. Create paper trade logs

## API / Events Needed
- `GET /paper/portfolio`
- `POST /paper/reset`

## Data Display / Data Stored
- Paper balance
- Paper positions
- Paper trades

## Acceptance Criteria
- [ ] Binance order endpoints are not called
- [ ] PnL can be calculated
- [ ] Portfolio can be reset

## Priority
MVP Core
