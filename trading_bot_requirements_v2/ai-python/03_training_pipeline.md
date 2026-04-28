# AI Service - Training Pipeline

## Purpose
train model เพื่อสร้าง trading signal

## Functional Requirements
1. รองรับ model เริ่มต้น เช่น RandomForest, XGBoost/LightGBM ถ้าติดตั้ง
2. train จาก dataset ที่เลือก
3. บันทึก metrics
4. บันทึก model artifact
5. รองรับ training job status

## API / Events Needed
- `POST /ai/train`
- `GET /ai/training-jobs/{id}`

## Data Display / Data Stored
- Training config
- Metrics
- Model artifact

## Acceptance Criteria
- [ ] train model ได้สำเร็จ
- [ ] มี validation metrics
- [ ] save artifact พร้อมใช้งาน inference

## Priority
MVP Core
