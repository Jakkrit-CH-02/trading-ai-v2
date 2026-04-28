# AI Service - Dataset Builder

## Purpose
Prepare datasets from historical market data for AI training.

## Functional Requirements
1. Load candles from the database
2. Select symbol/timeframe/date range
3. Create labels, such as next candle direction or future return
4. Split train/validation/test sets
5. Store dataset metadata

## API / Events Needed
- `POST /ai/datasets/build`
- `GET /ai/datasets`

## Data Display / Data Stored
- OHLCV
- Labels
- Dataset metadata

## Acceptance Criteria
- [ ] Datasets can be recreated
- [ ] Basic data leakage is avoided
- [ ] Metadata is complete

## Priority
MVP Core
