# Frontend Feature — Settings

## Phase
Phase 6 — Live Trading Safety

## Priority
MVP Core / Live Required

## Purpose
A page for basic system settings such as Binance API keys, default symbols, timeframes, risk limits, and notification channels.

## Why This Phase
This should be built before live trading because API keys, permissions, and risk config must be configured safely before using real money.

## Functional Requirements
1. Configure Binance API keys securely
2. Display API keys in masked form
3. Test Binance API key permissions
4. Select default symbols
5. Set the default timeframe
6. Set risk limits
7. Set notification channels
8. Display API permission status
9. Show validation errors before saving

## UI Requirements
- Never display the full secret key
- Never store secrets in localStorage
- The API key form must require confirmation
- The risk config form must validate clearly

## API / Events
```http
GET  /api/settings
PUT  /api/settings
POST /api/settings/binance-key/test
```

## Data Display
- API key status
- Default symbols
- Default timeframe
- Risk config
- Notification config
- Permission status

## Dependencies
- Backend Settings Service
- Backend Auth/User
- Backend Binance Connector
- Backend Audit Log

## Deliverables
- `SettingsPage`
- `ApiKeySettingsForm`
- `RiskSettingsForm`
- `NotificationSettingsForm`
- `PermissionStatusCard`

## Acceptance Criteria
- Config can be saved
- The full secret key is not shown in the UI
- Binance API keys can be tested
- Settings updates must have audit logs
