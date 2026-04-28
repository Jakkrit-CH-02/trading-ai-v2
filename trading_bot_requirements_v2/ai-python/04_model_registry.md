# AI Service - Model Registry

## Purpose
Manage versions of trained models.

## Functional Requirements
1. Store model versions
2. Store metadata, such as dataset, features, and metrics
3. Specify the active model for paper/live
4. Support model rollback
5. Prevent deployment of models with metrics below the threshold

## API / Events Needed
- `GET /ai/models`
- `POST /ai/models/{id}/activate`

## Data Display / Data Stored
- Model version
- Metrics
- Status
- Artifact path

## Acceptance Criteria
- [ ] All models can be viewed
- [ ] Models can be activated/rolled back
- [ ] The production model is identifiable

## Priority
MVP Core
