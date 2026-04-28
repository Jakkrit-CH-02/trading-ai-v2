# Frontend - AI Training Page

## Purpose
หน้าสำหรับสั่ง train AI และดูสถานะ training

## Functional Requirements
1. เลือก dataset, symbol, timeframe, date range
2. เลือก feature set
3. เลือก model type
4. สั่ง start training
5. แสดง training progress
6. แสดง evaluation metrics
7. เลือก promote model to paper/live ในอนาคต

## API / Events Needed
- `POST /api/ai/train`
- `GET /api/ai/training-jobs/{id}`
- `GET /api/ai/models`

## Data Display / Data Stored
- Training status
- Model metrics
- Dataset config

## Acceptance Criteria
- [ ] สั่ง train ได้จาก UI
- [ ] เห็น progress และผลลัพธ์
- [ ] ไม่สามารถ deploy model ที่ยังไม่ผ่าน evaluation

## Priority
MVP Core
