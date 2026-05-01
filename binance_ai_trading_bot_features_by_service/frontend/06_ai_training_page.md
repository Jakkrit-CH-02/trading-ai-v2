# Frontend Feature — AI Training Page

## Phase
Phase 3 — AI Training + Inference

## Priority
MVP Core

## Purpose
A page for starting AI training and viewing training status/model metrics.

## Why This Phase
This should be built after the Dataset Builder and Feature Engineering because datasets and feature schemas must exist before training can start.

## Functional Requirements
1. Select dataset
2. Select symbol
3. Select timeframe
4. Select date range
5. Select feature set
6. Select model type:
   - RandomForest
   - Logistic Regression baseline
   - XGBoost optional
   - LightGBM optional
7. Start training
8. Display training progress
9. Display evaluation metrics
10. Display the model list
11. Promote models to paper/live in the future

## UI Requirements
- The training form must have clearly separated sections
- Display job status as steps/status chips
- The model registry table must show versions and metrics
- The activate button must be disabled if the model has not passed evaluation

## API / Events
```http
POST /api/ai/train
GET  /api/ai/training-jobs/:id
GET  /api/ai/models
POST /api/ai/models/:id/activate
```

## Data Display
- Training status
- Training config
- Dataset config
- Model metrics
- Model version
- Active model status

## Dependencies
- AI Dataset Builder
- AI Feature Engineering
- AI Training Pipeline
- AI Model Registry
- Backend API proxy

## Deliverables
- `AITrainingPage`
- `TrainingConfigForm`
- `TrainingJobStatusCard`
- `ModelRegistryTable`
- `ModelMetricsPanel`

## Acceptance Criteria
- Training can be started from the UI
- Progress and results are visible
- Models that have not passed evaluation cannot be deployed
- Show the error reason when training fails
