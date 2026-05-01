# AI Service Feature — Inference API

## Phase
Phase 3 — AI Training + Inference

## Priority
MVP Core

## Purpose
Allow the backend to call AI analysis on the latest data.

## Why This Phase
This must be built after an active model exists in the Model Registry so the Strategy Engine can use AI signals.

## Functional Requirements
1. Receive the latest market features
2. Validate feature schema
3. Load the active model
4. Return signal:
   - BUY
   - SELL
   - HOLD
5. Return confidence
6. Return risk score
7. Return model version
8. Return explanation
9. Latency is low enough for the selected timeframe
10. Fallback when the model is unavailable

## API / Events
```http
POST /ai/inference
```

## Request Example
```json
{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "features": {
    "rsi_14": 42.5,
    "ema_20": 64500.1,
    "ema_50": 64120.8,
    "volume_ratio": 1.4
  }
}
```

## Response Example
```json
{
  "symbol": "BTCUSDT",
  "timeframe": "5m",
  "signal": "BUY",
  "confidence": 0.76,
  "risk_score": 0.32,
  "model_version": "model_001",
  "reason": "EMA trend positive and RSI not overbought",
  "top_features": ["ema_trend", "rsi_14", "volume_ratio"]
}
```

## Data Stored
- Inference request log optional
- Signal
- Confidence
- Risk score
- Model version
- Explanation

## Dependencies
- Feature Engineering
- Model Registry
- Signal Explanation

## Deliverables
- Inference endpoint
- Active model loader
- Schema validator
- Prediction mapper
- Fallback handler

## Acceptance Criteria
- The backend can call inference
- Response schema is stable
- Mismatched feature schemas must be rejected
- A fallback exists when the model is unavailable
