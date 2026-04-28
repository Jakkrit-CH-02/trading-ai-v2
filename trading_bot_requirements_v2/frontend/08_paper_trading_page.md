# Frontend - Paper Trading Page

## Purpose
Page for displaying a simulated portfolio before using real money.

## Functional Requirements
1. Display simulated balance
2. Display simulated open positions
3. Display paper trade history
4. Display performance report
5. Allow portfolio reset based on permissions

## API / Events Needed
- `GET /api/paper/portfolio`
- `GET /api/paper/trades`
- `POST /api/paper/reset`

## Data Display / Data Stored
- Simulated balance
- Paper positions
- Paper PnL

## Acceptance Criteria
- [ ] Portfolio simulation works without sending real orders
- [ ] Paper and live data are clearly separated
- [ ] Paper trading PnL is displayed

## Priority
MVP Core
