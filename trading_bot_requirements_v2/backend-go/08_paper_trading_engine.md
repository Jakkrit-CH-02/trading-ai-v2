# Backend - Paper Trading Engine

## Purpose
จำลองการเทรดโดยไม่ใช้เงินจริง

## Functional Requirements
1. จำลอง balance
2. จำลอง fill price จาก market data
3. คำนวณ fee/slippage
4. จัดการ open/closed positions
5. สร้าง paper trade logs

## API / Events Needed
- `GET /paper/portfolio`
- `POST /paper/reset`

## Data Display / Data Stored
- Paper balance
- Paper positions
- Paper trades

## Acceptance Criteria
- [ ] ไม่เรียก Binance order endpoint
- [ ] PnL คำนวณได้
- [ ] reset portfolio ได้

## Priority
MVP Core
