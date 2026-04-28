# Frontend - AI Training Page

## Purpose
Page for starting AI training and viewing training status.

## Functional Requirements
1. Select dataset, symbol, timeframe, and date range
2. Select feature set
3. Select model type
4. Start training
5. Display training progress
6. Display evaluation metrics
7. Support promoting a model to paper/live in the future

## API / Events Needed
- `POST /api/ai/train`
- `GET /api/ai/training-jobs/{id}`
- `GET /api/ai/models`

## Data Display / Data Stored
- Training status
- Model metrics
- Dataset config

## Acceptance Criteria
- [ ] Users can start training from the UI
- [ ] Progress and results are visible
- [ ] Models that have not passed evaluation cannot be deployed

## Priority
MVP Core
