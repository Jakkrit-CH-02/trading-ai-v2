# Backend Feature — Bot Runtime Manager

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core / Safety Critical

## Purpose
Control bot runtime state such as start, stop, pause, and selected mode/strategy/symbol/timeframe.

## Why This Phase
This is required so the Bot Control Page can control the execution loop safely.

## Functional Requirements
1. Start bot
2. Stop bot
3. Pause bot
4. Resume bot in the future
5. Select mode:
   - backtest
   - paper
   - live
6. Select strategy
7. Select symbol/timeframe
8. Store runtime status
9. Run the strategy loop by timeframe
10. Check the kill switch before running
11. Send status updates through WebSocket

## API / Events
```http
POST /api/bot/start
POST /api/bot/stop
POST /api/bot/pause
GET  /api/bot/status
WS   /ws/dashboard
```

## Data Stored
- Bot status
- Runtime config
- Current mode
- Selected strategy
- Selected symbols
- Last signal
- Last error

## Dependencies
- Strategy Engine
- Risk Engine
- Order Manager
- Auth/User
- Alert Service
- Settings Service

## Deliverables
- Runtime state machine
- Bot control API
- Execution loop
- Status broadcaster
- Safety guard

## Acceptance Criteria
- Start/stop/pause work correctly
- Live mode must pass guards
- The kill switch must stop execution
- Status must match the Dashboard/Bot Control pages
