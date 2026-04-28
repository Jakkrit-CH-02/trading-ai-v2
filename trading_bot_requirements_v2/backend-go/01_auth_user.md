# Backend - Auth / User

## Purpose
จัดการผู้ใช้ สิทธิ์ และ session สำหรับระบบ dashboard

## Functional Requirements
1. รองรับ login/logout
2. จัดการ role เช่น admin, viewer
3. ป้องกัน endpoint สำคัญด้วย authentication
4. เก็บ audit log สำหรับ action สำคัญ

## API / Events Needed
- `POST /auth/login`
- `POST /auth/logout`
- `GET /auth/me`

## Data Display / Data Stored
- User profile
- Role
- Session
- Audit log

## Acceptance Criteria
- [ ] endpoint สำคัญต้อง auth
- [ ] role จำกัด action ได้
- [ ] มี audit log สำหรับ start/stop/live

## Priority
MVP Core
