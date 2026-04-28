# AI Service - Training Pipeline

## Purpose
Train models to generate trading signals.

## Functional Requirements
1. Support initial models, such as RandomForest and XGBoost/LightGBM if installed
2. Train from the selected dataset
3. Store metrics
4. Store model artifacts
5. Support training job status

## API / Events Needed
- `POST /ai/train`
- `GET /ai/training-jobs/{id}`

## Data Display / Data Stored
- Training config
- Metrics
- Model artifact

## Acceptance Criteria
- [ ] Models can be trained successfully
- [ ] Validation metrics are available
- [ ] Artifacts are saved and ready for inference

## Priority
MVP Core
