# Backend - Binance Connector

## Purpose
เชื่อมต่อ Binance REST API และ WebSocket

## Functional Requirements
1. เชื่อม REST API สำหรับ account/order/exchange info
2. เชื่อม WebSocket สำหรับ market stream
3. รองรับ reconnect
4. จัดการ rate limit
5. รองรับ testnet/mainnet config
6. validate API key permission

## API / Events Needed
- `Internal Binance client`

## Data Display / Data Stored
- Exchange info
- Account info
- Market stream
- Order response

## Acceptance Criteria
- [ ] ดึงข้อมูลตลาดได้
- [ ] reconnect เมื่อ WebSocket หลุด
- [ ] ไม่เกิน rate limit โดยไม่จำเป็น

## Priority
MVP Core
