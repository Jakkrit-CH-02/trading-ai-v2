# AI Service - Backtest AI Evaluation

## Purpose
Evaluate AI models against historical data together with strategy/risk rules.

## Functional Requirements
1. Use the model to generate signals on historical data
2. Send signals to the backtest engine or simulate internally
3. Measure win rate, profit factor, and drawdown
4. Compare against a baseline strategy
5. Create an evaluation report

## API / Events Needed
- `POST /ai/evaluate`
- `GET /ai/evaluations/{id}`

## Data Display / Data Stored
- Model predictions
- Backtest metrics
- Evaluation report

## Acceptance Criteria
- [ ] Models must pass evaluation before use
- [ ] Results can be compared against the baseline
- [ ] Reports can be stored

## Priority
MVP Core
