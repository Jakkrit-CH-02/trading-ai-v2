# Backend - Bot Runtime Controller

## Purpose
Control the bot lifecycle.

## Functional Requirements
1. start/stop/pause/resume bot
2. Manage runtime state
3. Prevent duplicate starts
4. Check dependency health before start
5. Store runtime events

## API / Events Needed
- `POST /bot/start`
- `POST /bot/stop`
- `GET /bot/status`

## Data Display / Data Stored
- Runtime state
- Mode
- Strategy
- Health status

## Acceptance Criteria
- [ ] Bot control is safe
- [ ] State is correct
- [ ] Bot cannot start if dependencies are not ready

## Priority
MVP Core
