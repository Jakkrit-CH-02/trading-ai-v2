# Frontend - Settings

## Purpose
Page for configuring basic system settings.

## Functional Requirements
1. Configure Binance API keys securely
2. Select default symbols
3. Configure the default timeframe
4. Configure risk limits
5. Configure notification channels
6. Display API permission status

## API / Events Needed
- `GET /api/settings`
- `PUT /api/settings`
- `POST /api/settings/binance-key/test`

## Data Display / Data Stored
- API key status
- Default config
- Risk config

## Acceptance Criteria
- [ ] Configuration can be saved
- [ ] Full secret keys are not displayed in the UI
- [ ] Binance API keys can be tested

## Priority
MVP Core
