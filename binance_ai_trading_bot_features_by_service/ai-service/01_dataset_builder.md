# AI Service Feature — Dataset Builder

## Phase
Phase 2 — AI Dataset + Feature Engineering

## Priority
MVP Core

## Purpose
Prepare datasets from historical market data for AI training.

## Why This Phase
This must be built before training because models require datasets with correct labels, splits, and metadata.

## Functional Requirements
1. Load candles from the database/backend
2. Select symbol
3. Select timeframe
4. Select date range
5. Create labels:
   - next candle direction
   - future return
   - threshold movement
6. Split dataset:
   - train
   - validation
   - test
7. Save dataset metadata
8. Prevent data leakage
9. Allow datasets to be rebuilt with the same config

## API / Events
```http
POST /ai/datasets/build
GET  /ai/datasets
GET  /ai/datasets/:id
```

## Data Stored
- OHLCV
- Labels
- Dataset metadata
- Split metadata
- Build config

## Dependencies
- Backend Market Data Service
- Database or data export
- Feature Engineering in the next step

## Deliverables
- Dataset builder module
- Label generator
- Time-based splitter
- Dataset metadata storage

## Acceptance Criteria
- Datasets can be rebuilt
- No basic data leakage exists
- Metadata is complete
- Train/test splits must be ordered by time
