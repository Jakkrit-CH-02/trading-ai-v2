# AI Service - Backtest AI Evaluation

## Purpose
ประเมิน AI model กับข้อมูลย้อนหลังร่วมกับ strategy/risk rules

## Functional Requirements
1. นำ model ไปสร้าง signal บน historical data
2. ส่ง signal เข้า backtest engine หรือจำลองเอง
3. วัด win rate, profit factor, drawdown
4. เปรียบเทียบกับ baseline strategy
5. สร้าง evaluation report

## API / Events Needed
- `POST /ai/evaluate`
- `GET /ai/evaluations/{id}`

## Data Display / Data Stored
- Model predictions
- Backtest metrics
- Evaluation report

## Acceptance Criteria
- [ ] model ต้องผ่าน evaluation ก่อนใช้งาน
- [ ] เห็นผลเทียบ baseline
- [ ] เก็บ report ได้

## Priority
MVP Core
