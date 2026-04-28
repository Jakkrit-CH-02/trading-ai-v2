# Frontend - Risk Monitor

## Purpose
Page for displaying and monitoring system risk.

## Functional Requirements
1. Display max daily loss
2. Display current drawdown
3. Display risk per trade
4. Display leverage and position size
5. Display the number of open positions
6. Notify users when risk approaches a limit
7. Provide an emergency stop/kill switch button in the live phase

## API / Events Needed
- `GET /api/risk/status`
- `POST /api/risk/kill-switch`
- `WS /ws/risk`

## Data Display / Data Stored
- Drawdown
- Daily loss
- Position exposure
- Risk limits

## Acceptance Criteria
- [ ] Risk status is clearly visible
- [ ] Warnings are displayed when thresholds are exceeded
- [ ] Risk values match the backend

## Priority
MVP Core
