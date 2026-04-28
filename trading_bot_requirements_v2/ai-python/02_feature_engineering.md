# AI Service - Feature Engineering

## Purpose
สร้าง features สำหรับ model จากข้อมูลราคาและ volume

## Functional Requirements
1. คำนวณ RSI, MACD, EMA, ATR, Bollinger Bands
2. สร้าง return/volatility features
3. สร้าง volume spike features
4. normalize/scale features
5. บันทึก feature schema

## API / Events Needed
- `Internal feature pipeline`

## Data Display / Data Stored
- Technical indicators
- Feature matrix
- Feature schema

## Acceptance Criteria
- [ ] features train/inference ใช้ schema เดียวกัน
- [ ] จัดการ missing value ได้
- [ ] คำนวณ indicator ถูกต้อง

## Priority
MVP Core
