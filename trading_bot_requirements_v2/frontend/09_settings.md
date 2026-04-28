# Frontend - Settings

## Purpose
หน้าตั้งค่าระบบพื้นฐาน

## Functional Requirements
1. ตั้ง Binance API key แบบปลอดภัย
2. เลือก default symbols
3. ตั้ง default timeframe
4. ตั้ง risk limits
5. ตั้ง notification channel
6. แสดง API permission status

## API / Events Needed
- `GET /api/settings`
- `PUT /api/settings`
- `POST /api/settings/binance-key/test`

## Data Display / Data Stored
- API key status
- Default config
- Risk config

## Acceptance Criteria
- [ ] บันทึก config ได้
- [ ] ไม่แสดง secret key เต็มบน UI
- [ ] ทดสอบ Binance API key ได้

## Priority
MVP Core
