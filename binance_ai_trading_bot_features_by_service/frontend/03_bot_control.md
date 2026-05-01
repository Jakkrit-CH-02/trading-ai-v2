# Frontend Feature — Bot Control

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core / Safety Critical

## Purpose
A page for controlling bot operation, such as start, stop, pause, and selecting mode/strategy/symbol/timeframe/risk.

## Why This Phase
This should be built after the Strategy Engine, Risk Engine, and Paper Trading Engine because bot controls must be connected to the real runtime.

## Functional Requirements
1. Start bot
2. Stop bot
3. Pause bot
4. Select mode:
   - backtest
   - paper
   - live
5. Select strategy
6. Select symbol
7. Select timeframe
8. Set risk per trade
9. Display the latest runtime status
10. Show confirmation before enabling live trading
11. Show an error message when the backend rejects a command

## UI Requirements
- Provide a clear control panel
- Live mode must show a danger confirmation modal
- Viewer role must see controls as disabled
- Display runtime state as a status chip

## API / Events
```http
POST /api/bot/start
POST /api/bot/stop
POST /api/bot/pause
GET  /api/bot/status
GET  /api/strategies
```

## Data Display
- Bot mode
- Selected strategy
- Selected symbol/timeframe
- Runtime state
- Risk config
- Last signal
- Last error

## Dependencies
- Backend Bot Runtime Manager
- Backend Strategy Engine
- Backend Risk Engine
- Backend Auth/User
- Backend Settings

## Deliverables
- `BotControlPage`
- `ModeSelector`
- `StrategySelector`
- `RiskConfigForm`
- `RuntimeStatusCard`
- `LiveTradingConfirmDialog`

## Acceptance Criteria
- Start/stop/pause can be triggered from the UI
- Live trading cannot be enabled without confirmation
- Backend rejections must show clear errors
- Viewer role cannot control the bot
