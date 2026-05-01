# Backend Feature — Strategy Engine

## Phase
Phase 4 — Strategy + Risk + Paper Trading

## Priority
MVP Core

## Purpose
Process trade entry/exit rules by combining indicators, rules, and AI signals.

## Why This Phase
This should be built after the AI Inference API because strategies need AI signals together with rule filters to create final decisions.

## Functional Requirements
1. Load strategy config
2. Receive market snapshots
3. Call the AI Inference API
4. Calculate signals:
   - BUY
   - SELL
   - HOLD
5. Include rule filters:
   - RSI
   - EMA trend
   - MACD
   - volume spike
   - confidence threshold
6. Create signal reasons
7. Send signals to the Risk Engine for validation
8. Fall back to HOLD or rule-only mode when AI is unavailable

## API / Events
```http
GET /api/strategies
```

```text
Internal strategy runner
```

## Data Stored
- Strategy config
- Signal
- Signal reason
- AI confidence
- Model version

## Dependencies
- Market Data Service
- AI Inference API
- Risk Engine
- Settings Service

## Deliverables
- Strategy runner
- Strategy config loader
- Signal decision logic
- Signal reason builder

## Acceptance Criteria
- The strategy can generate signals
- Signal reasons are recorded
- Strategy config can be changed
- The system can fall back when AI is unavailable
