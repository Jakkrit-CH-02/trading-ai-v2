# Backend Feature — Auth / User

## Phase
Phase 6 — Live Trading Safety

## Priority
Security Core / Live Required

## Purpose
Manage users, sessions, permissions, and audit logs for the dashboard system.

## Why This Phase
This must be complete before live trading to prevent unauthorized users from starting, stopping, enabling live mode, or changing API keys.

## Functional Requirements
1. Support login
2. Support logout
3. Read the current user
4. Manage roles:
   - admin
   - trader
   - viewer
5. Protect sensitive endpoints with authentication
6. Use role guards to restrict actions
7. Store audit logs for important actions:
   - start bot
   - stop bot
   - pause bot
   - enable live trading
   - kill switch
   - settings update
   - API key update

## API
```http
POST /api/auth/login
POST /api/auth/logout
GET  /api/auth/me
GET  /api/audit-logs
```

## Data Stored
- User profile
- Role
- Session/token
- Audit log

## Dependencies
- Database
- Config Service
- Settings Service
- Bot Runtime Manager

## Deliverables
- Auth middleware
- Role guard
- Session/token handling
- Audit log repository
- Protected route middleware

## Acceptance Criteria
- Sensitive endpoints must require authentication
- Roles can restrict actions
- Viewers cannot control the bot
- Audit logs exist for start/stop/live/settings actions
