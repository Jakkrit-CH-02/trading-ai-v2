# Frontend - Trade Logs

## Purpose
Page for viewing the full order and trade history.

## Functional Requirements
1. Display the trade list as a table
2. Filter by symbol, strategy, mode, and date
3. Display entry, exit, quantity, fee, and PnL
4. Display the reason for entering the trade
5. Display AI confidence at trade entry
6. Support CSV export in the future

## API / Events Needed
- `GET /api/trades`
- `GET /api/orders`

## Data Display / Data Stored
- Trade ID
- Order ID
- Entry/exit price
- PnL
- Reason
- AI confidence

## Acceptance Criteria
- [ ] Users can search and filter trades
- [ ] PnL data displays correctly
- [ ] Users can open details for individual trades

## Priority
MVP Core
