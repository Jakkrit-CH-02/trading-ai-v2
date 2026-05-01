# Backend Feature — Settings Service

## Phase
Phase 6 — Live Trading Safety

## Priority
MVP Core / Live Required

## Purpose
Manage core system configuration such as Binance API keys, symbols, timeframes, risk config, and notification config.

## Why This Phase
This must be ready before live trading because live mode requires validated API keys and risk config.

## Functional Requirements
1. Read settings
2. Update settings
3. Encrypt API secrets
4. Mask secret keys before sending them to the frontend
5. Test Binance API key
6. Validate risk config
7. Validate default symbol/timeframe
8. Record an audit log for every change

## API / Events
```http
GET  /api/settings
PUT  /api/settings
POST /api/settings/binance-key/test
```

## Data Stored
- API key encrypted
- API key permission status
- Default symbols
- Default timeframe
- Risk config
- Notification config

## Dependencies
- Auth/User
- Binance Connector
- Audit Log
- Secure Credential Store

## Deliverables
- Settings API
- Secret encryption/masking
- API key tester
- Risk config validator
- Audit integration

## Acceptance Criteria
- API secrets must not be sent to the frontend
- Settings must be validated before saving
- Key tests must report permission status
- Every edit must have an audit log
