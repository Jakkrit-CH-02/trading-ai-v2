# Backend Feature — Paper Trading Engine

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core

## Purpose
Simulate trading without using real money.

## Why This Phase
This must be built before live trading to test strategy, risk, and order flow without risking real money.

## Functional Requirements
1. Simulate balance
2. Simulate equity
3. Simulate fill prices from market data
4. Calculate fees
5. Calculate slippage
6. Manage open positions
7. Manage closed positions
8. Calculate PnL
9. Create paper trade logs
10. Reset portfolio

## API / Events
```http
GET  /api/paper/portfolio
GET  /api/paper/trades
POST /api/paper/reset
```

## Data Stored
- Paper balance
- Paper positions
- Paper trades
- Paper PnL
- Performance summary

## Dependencies
- Market Data Service
- Order Manager
- Trade Log Service
- Auth/User

## Deliverables
- Simulated portfolio service
- Paper fill simulator
- PnL calculator
- Paper trade repository
- Reset portfolio action

## Acceptance Criteria
- Do not call Binance order endpoints
- PnL can be calculated
- Portfolio can be reset
- Paper/live data is clearly separated
