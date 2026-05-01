# Frontend Feature — Dashboard

## Phase
Phase 1 — Market Data + Dashboard MVP

## Priority
MVP Core

## Purpose
A minimal bot overview page that lets users immediately understand system status.

## Why This Phase
This should be built early because it is the main page for checking whether the backend, Binance connection, AI service, and database are ready.

## Functional Requirements
1. Display bot status: `running`, `paused`, `stopped`, `error`
2. Display balance, equity, unrealized PnL, and realized PnL
3. Display daily PnL and current drawdown
4. Display latest open positions
5. Display the latest AI signal with confidence
6. Display system health:
   - Binance connection
   - AI service
   - database
   - WebSocket
7. Support realtime updates through WebSocket
8. Include loading, empty, and error states

## UI Requirements
- Use React Vite + TypeScript
- Use MUI components and `sx`
- Use a minimal dashboard layout
- Use a card-based layout
- Display status with Chips
- Colors should be simple and uncluttered
- BUY = green, SELL = red, HOLD = gray/yellow

## API / Events
```http
GET /api/dashboard/summary
WS  /ws/dashboard
```

## Data Display
- Bot status
- Balance/equity
- PnL
- Drawdown
- Open positions
- Latest signal
- System health

## Dependencies
- Backend Market Data Service
- Backend Bot Runtime Status
- Backend Risk Engine
- Backend Alert Service
- AI Inference API

## Deliverables
- `DashboardPage`
- `SystemHealthCards`
- `PortfolioSummaryCard`
- `LatestSignalCard`
- `OpenPositionsCard`
- `RecentAlertsCard`

## Acceptance Criteria
- The system overview is visible on one page
- Important data refreshes in realtime or near realtime
- All loading/error states are displayed
- If Binance or the AI service is down, a clear warning is shown
