# Frontend - Bot Control

## Purpose
Page for controlling bot operations.

## Functional Requirements
1. Start, Stop, Pause bot
2. Select mode: backtest, paper, live
3. Select strategy
4. Select symbol and timeframe
5. Configure basic risk per trade
6. Show confirmation before enabling live trading
7. Display the latest runtime status

## API / Events Needed
- `POST /api/bot/start`
- `POST /api/bot/stop`
- `POST /api/bot/pause`
- `GET /api/bot/status`
- `GET /api/strategies`

## Data Display / Data Stored
- Bot mode
- Selected strategy
- Runtime state
- Risk config

## Acceptance Criteria
- [ ] Users can start/stop from the UI
- [ ] Live trading cannot be enabled without confirmation
- [ ] Error messages are displayed when the backend rejects a command

## Priority
MVP Core
