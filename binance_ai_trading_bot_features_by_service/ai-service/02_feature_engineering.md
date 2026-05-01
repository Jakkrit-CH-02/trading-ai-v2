# AI Service Feature — Feature Engineering

## Phase
Phase 2 — AI Dataset + Feature Engineering

## Priority
MVP Core

## Purpose
Create model features from price and volume data.

## Why This Phase
This must be built before the Training Pipeline and Inference API because training and inference must use the same feature schema.

## Functional Requirements
1. Calculate RSI
2. Calculate MACD
3. Calculate EMA
4. Calculate ATR
5. Calculate Bollinger Bands
6. Create return features
7. Create volatility features
8. Create volume spike features
9. Normalize/scale features
10. Save the feature schema
11. Handle missing values
12. Ensure feature order remains stable

## Internal Pipeline
```text
OHLCV
→ Technical Indicators
→ Feature Matrix
→ Scaling
→ Feature Schema
→ Dataset / Inference Input
```

## API / Events
```text
Internal feature pipeline
```

## Data Stored
- Technical indicators
- Feature matrix
- Feature schema
- Scaler artifact

## Dependencies
- Dataset Builder
- Training Pipeline
- Inference API

## Deliverables
- Indicator calculator
- Feature matrix builder
- Scaler/normalizer
- Feature schema registry
- Missing value handler

## Acceptance Criteria
- Training and inference features use the same schema
- Missing values can be handled
- Indicators are calculated correctly
- Feature order must remain stable
