# Backend - Strategy Engine

## Purpose
ประมวลผลกฎการเข้าออก trade

## Functional Requirements
1. โหลด strategy config
2. คำนวณ signal จาก indicator/AI
3. รองรับ BUY/SELL/HOLD
4. มี rule filter เช่น RSI, EMA, volume
5. ส่ง signal ให้ risk engine ตรวจต่อ

## API / Events Needed
- `Internal strategy runner`
- `GET /strategies`

## Data Display / Data Stored
- Strategy config
- Signal
- Reason

## Acceptance Criteria
- [ ] strategy สร้าง signal ได้
- [ ] บันทึก reason ของ signal
- [ ] เปลี่ยน strategy config ได้

## Priority
MVP Core
