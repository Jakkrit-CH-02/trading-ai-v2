# AI Service - Signal Explanation

## Purpose
Explain signal reasons to support debugging and dashboard display.

## Functional Requirements
1. Create explanations from feature importance/rules
2. Display top factors affecting the signal
3. Store explanations with trade logs
4. Support simple explanations in the MVP

## API / Events Needed
- `Included in /ai/inference response`

## Data Display / Data Stored
- Signal reason
- Top features
- Confidence explanation

## Acceptance Criteria
- [ ] Every signal has a basic reason
- [ ] The frontend can display the reason
- [ ] Model debugging is supported

## Priority
MVP Core
