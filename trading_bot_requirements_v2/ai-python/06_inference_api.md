# AI Service - Inference API

## Purpose
ให้ backend เรียก AI วิเคราะห์ข้อมูลล่าสุด

## Functional Requirements
1. รับ market features ล่าสุด
2. โหลด active model
3. ตอบ signal BUY/SELL/HOLD
4. ตอบ confidence และ risk score
5. ตอบ latency ต่ำพอสำหรับ timeframe ที่ใช้

## API / Events Needed
- `POST /ai/inference`

## Data Display / Data Stored
- Input features
- Signal
- Confidence
- Risk score

## Acceptance Criteria
- [ ] backend เรียก inference ได้
- [ ] response schema คงที่
- [ ] มี fallback เมื่อ model unavailable

## Priority
MVP Core
