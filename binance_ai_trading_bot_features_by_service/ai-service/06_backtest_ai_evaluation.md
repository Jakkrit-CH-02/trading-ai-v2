# AI Service Feature — Backtest AI Evaluation

## Phase
Phase 5 — Backtesting + Evaluation

## Priority
MVP Core

## Purpose
Evaluate AI models against historical data together with strategy/risk rules.

## Why This Phase
This must be done before promoting models to live to confirm that the model beats the baseline and is not too risky.

## Functional Requirements
1. Load model version
2. Load historical dataset
3. Use the model to generate signals on historical data
4. Send signals to the backtest engine or simulate them internally
5. Measure metrics:
   - win rate
   - profit factor
   - max drawdown
   - total return
   - average trade return
6. Compare against the baseline strategy
7. Create an evaluation report
8. Block models that do not meet the criteria

## API / Events
```http
POST /ai/evaluate
GET  /ai/evaluations/:id
```

## Data Stored
- Model predictions
- Backtest metrics
- Evaluation report
- Baseline comparison
- Pass/fail status

## Dependencies
- Model Registry
- Dataset Builder
- Feature Engineering
- Backend Backtest Engine optional

## Deliverables
- Evaluation runner
- Baseline comparator
- Metrics calculator
- Evaluation report storage
- Model promotion gate

## Acceptance Criteria
- Models must pass evaluation before use
- Baseline comparison results are visible
- Reports can be stored
- Reports must be linked to model versions
