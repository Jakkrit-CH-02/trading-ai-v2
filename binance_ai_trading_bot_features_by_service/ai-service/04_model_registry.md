# AI Service Feature — Model Registry

## Phase
Phase 3 — AI Training + Inference

## Priority
MVP Core

## Purpose
Manage versions of trained models.

## Why This Phase
This is required after the Training Pipeline because trained models must be versioned, activated, rolled back, and quality-checked before use.

## Functional Requirements
1. Save model versions
2. Store metadata:
   - dataset id
   - feature schema id
   - metrics
   - artifact path
   - created at
3. Define the active model for paper mode
4. Define the active model for live mode
5. Models can be rolled back
6. Prevent deployment of models whose metrics are below the threshold
7. Link evaluation results before live promotion

## API / Events
```http
GET  /ai/models
GET  /ai/models/:id
POST /ai/models/:id/activate
POST /ai/models/:id/rollback
```

## Data Stored
- Model version
- Metrics
- Status
- Artifact path
- Active target: paper/live
- Evaluation status

## Dependencies
- Training Pipeline
- Backtest AI Evaluation
- Inference API

## Deliverables
- Model metadata repository
- Activate model API
- Rollback API
- Promotion guard
- Active model resolver

## Acceptance Criteria
- All models can be viewed
- Models can be activated/rolled back
- The production model is identifiable
- Live models must pass evaluation first
