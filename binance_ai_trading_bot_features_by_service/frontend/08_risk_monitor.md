# Frontend Feature — Risk Monitor

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core / Safety Critical

## Purpose
A page for displaying and monitoring system risk.

## Why This Phase
This should be built alongside the Risk Engine because it is an important page for checking whether the bot is exceeding risk limits.

## Functional Requirements
1. Display max daily loss
2. Display current daily loss
3. Display current drawdown
4. Display risk per trade
5. Display leverage
6. Display position size
7. Display the number of open positions
8. Warn when risk approaches the limit
9. Display critical state when limits are exceeded
10. Include an emergency stop/kill switch button in the live phase

## UI Requirements
- Use risk cards
- Warning/critical states must be clear
- Kill switch must use a confirmation modal
- Display realtime risk updates

## API / Events
```http
GET  /api/risk/status
POST /api/risk/kill-switch
WS   /ws/risk
```

## Data Display
- Drawdown
- Daily loss
- Position exposure
- Risk limits
- Open positions
- Kill switch status

## Dependencies
- Backend Risk Engine
- Backend Order Manager
- Backend Bot Runtime Manager
- Backend Alert Service

## Deliverables
- `RiskMonitorPage`
- `RiskSummaryCards`
- `RiskLimitProgress`
- `RiskWarningBanner`
- `KillSwitchDialog`

## Acceptance Criteria
- Risk status is clearly visible
- Display warnings when thresholds are exceeded
- Risk values match the backend
- The kill switch must block orders immediately
