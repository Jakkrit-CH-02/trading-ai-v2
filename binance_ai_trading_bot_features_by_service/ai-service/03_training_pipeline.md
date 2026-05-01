# AI Service Feature — Training Pipeline

## Phase
Phase 3 — AI Training + Inference

## Priority
MVP Core

## Purpose
Train models to generate trading signals.

## Why This Phase
This should be built after the Dataset Builder and Feature Engineering because prepared datasets/features are required.

## Functional Requirements
1. Receive training config
2. Load dataset
3. Load feature schema
4. Support initial models:
   - RandomForest
   - Logistic Regression baseline
   - XGBoost optional
   - LightGBM optional
5. Train the model from the selected dataset
6. Validate model
7. Save metrics
8. Save model artifacts
9. Update training job status
10. Save the error reason when failed

## API / Events
```http
POST /ai/train
GET  /ai/training-jobs/:id
```

## Training Status
```text
queued
running
completed
failed
cancelled
```

## Data Stored
- Training config
- Metrics
- Model artifact
- Training logs
- Job status

## Dependencies
- Dataset Builder
- Feature Engineering
- Model Registry

## Deliverables
- Training job runner
- Model trainer
- Metrics evaluator
- Artifact saver
- Job status API

## Acceptance Criteria
- Models can be trained successfully
- Validation metrics exist
- Artifacts are saved and ready for inference
- Training failures must include an error reason
