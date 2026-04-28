# Frontend - Dashboard

## Purpose
A minimal overview page for bot operations so users can immediately understand the system status.

## Functional Requirements
1. Display bot status: running, paused, stopped, error
2. Display balance, equity, unrealized PnL, and realized PnL
3. Display the latest open positions
4. Display the latest AI signal and confidence
5. Display daily PnL and drawdown
6. Display system health, such as Binance connection, AI service, and database

## API / Events Needed
- `GET /api/dashboard/summary`
- `WS /ws/dashboard`

## Data Display / Data Stored
- Bot status
- Balance/equity
- PnL
- Open positions
- Latest signal

## Acceptance Criteria
- [ ] Users can see the system overview on a single page
- [ ] Important data refreshes in real time or near real time
- [ ] Loading and error states are available

## Priority
MVP Core
