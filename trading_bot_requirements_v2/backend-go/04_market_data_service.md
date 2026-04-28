# Backend - Market Data Service

## Purpose
ให้บริการข้อมูลตลาดแก่ frontend และ engine อื่น

## Functional Requirements
1. อ่าน candles จาก database/cache
2. ส่ง realtime price/candle ผ่าน WebSocket
3. คำนวณ indicator เบื้องต้น
4. ให้ API สำหรับ latest market snapshot

## API / Events Needed
- `GET /market/candles`
- `GET /market/snapshot`
- `WS /ws/market`

## Data Display / Data Stored
- Candles
- Latest price
- Indicators

## Acceptance Criteria
- [ ] frontend ดึงกราฟได้เร็ว
- [ ] WebSocket ส่งข้อมูลต่อเนื่อง
- [ ] รองรับหลาย client

## Priority
MVP Core
