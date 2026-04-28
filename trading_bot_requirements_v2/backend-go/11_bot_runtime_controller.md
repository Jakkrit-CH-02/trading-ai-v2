# Backend - Bot Runtime Controller

## Purpose
ควบคุม lifecycle ของ bot

## Functional Requirements
1. start/stop/pause/resume bot
2. จัดการ runtime state
3. ป้องกันการ start ซ้ำ
4. ตรวจ health dependency ก่อน start
5. บันทึก runtime events

## API / Events Needed
- `POST /bot/start`
- `POST /bot/stop`
- `GET /bot/status`

## Data Display / Data Stored
- Runtime state
- Mode
- Strategy
- Health status

## Acceptance Criteria
- [ ] ควบคุม bot ได้ปลอดภัย
- [ ] state ถูกต้อง
- [ ] start ไม่ได้ถ้า dependency ไม่พร้อม

## Priority
MVP Core
