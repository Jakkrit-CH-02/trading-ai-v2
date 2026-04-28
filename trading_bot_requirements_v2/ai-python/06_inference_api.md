# AI Service - Inference API

## Purpose
Allow the backend to call AI analysis for the latest data.

## Functional Requirements
1. Receive the latest market features
2. Load the active model
3. Return BUY/SELL/HOLD signals
4. Return confidence and risk score
5. Return responses with latency low enough for the selected timeframe

## API / Events Needed
- `POST /ai/inference`

## Data Display / Data Stored
- Input features
- Signal
- Confidence
- Risk score

## Acceptance Criteria
- [ ] The backend can call inference
- [ ] The response schema is stable
- [ ] A fallback exists when the model is unavailable

## Priority
MVP Core
