# Frontend Feature — Paper Trading Page

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core

## Purpose
A page showing the simulated portfolio before using real money.

## Why This Phase
This should be built before live trading so strategies and AI signals can be tested without sending real orders to Binance.

## Functional Requirements
1. Display simulated balance
2. Display simulated equity
3. Display simulated open positions
4. Display paper trade history
5. Display paper PnL
6. Display the performance report
7. Allow portfolio reset based on permission
8. Display a clear badge indicating paper mode

## UI Requirements
- Clearly separate paper/live modes
- Use a badge or banner that says `PAPER TRADING`
- Reset must require confirmation
- Display PnL positive/negative

## API / Events
```http
GET  /api/paper/portfolio
GET  /api/paper/trades
POST /api/paper/reset
```

## Data Display
- Simulated balance
- Simulated equity
- Paper positions
- Paper PnL
- Paper trade history
- Performance summary

## Dependencies
- Backend Paper Trading Engine
- Backend Order Manager
- Backend Trade Log Service
- Backend Auth/User

## Deliverables
- `PaperTradingPage`
- `PaperPortfolioSummary`
- `PaperPositionTable`
- `PaperTradeHistory`
- `ResetPaperPortfolioDialog`

## Acceptance Criteria
- The portfolio can be simulated without sending real orders
- Paper and live data are clearly separated
- Paper trading PnL is displayed correctly
- Resetting the portfolio requires permission
