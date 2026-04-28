# Backend - Strategy Engine

## Purpose
Process trade entry and exit rules.

## Functional Requirements
1. Load strategy configuration
2. Calculate signals from indicators/AI
3. Support BUY/SELL/HOLD
4. Provide rule filters, such as RSI, EMA, and volume
5. Send signals to the risk engine for validation

## API / Events Needed
- `Internal strategy runner`
- `GET /strategies`

## Data Display / Data Stored
- Strategy config
- Signal
- Reason

## Acceptance Criteria
- [ ] Strategies can generate signals
- [ ] Signal reasons are stored
- [ ] Strategy configuration can be changed

## Priority
MVP Core
