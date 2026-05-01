# AI Service Feature — Signal Explanation

## Phase
Phase 3 — AI Training + Inference

## Priority
MVP Core

## Purpose
Explain signal reasons to help debugging and display them on the dashboard/trade log.

## Why This Phase
This should be built together with the Inference API because every signal should have a reason for later review.

## Functional Requirements
1. Create explanations from feature importance
2. Create explanations from strategy/rule context
3. Display the top factors affecting the signal
4. Record explanations with trade logs
5. Support simple explanations in the MVP
6. Return confidence explanation

## API / Events
```text
Included in /ai/inference response
```

## Response Example
```json
{
  "reason": "EMA trend positive and RSI not overbought",
  "top_features": ["ema_20_above_ema_50", "rsi_14", "volume_ratio"],
  "confidence_explanation": "confidence is high because trend and volume features align"
}
```

## Data Stored
- Signal reason
- Top features
- Confidence explanation

## Dependencies
- Inference API
- Feature Engineering
- Model Registry
- Trade Log Service

## Deliverables
- Explanation builder
- Top feature extractor
- Rule explanation mapper
- Inference response integration

## Acceptance Criteria
- Every signal has a basic reason
- The frontend can display reasons
- Model debugging is supported
- Trade logs must keep explanations for later review
