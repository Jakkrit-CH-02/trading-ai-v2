# AI Service - Model Registry

## Purpose
จัดการ version ของ model ที่ train แล้ว

## Functional Requirements
1. บันทึก model version
2. เก็บ metadata เช่น dataset, features, metrics
3. ระบุ active model สำหรับ paper/live
4. rollback model ได้
5. ป้องกัน deploy model ที่ metric ต่ำกว่าเกณฑ์

## API / Events Needed
- `GET /ai/models`
- `POST /ai/models/{id}/activate`

## Data Display / Data Stored
- Model version
- Metrics
- Status
- Artifact path

## Acceptance Criteria
- [ ] ดู model ทั้งหมดได้
- [ ] activate/rollback ได้
- [ ] รู้ว่า production ใช้ model ใด

## Priority
MVP Core
