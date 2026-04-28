# Backend - Auth / User

## Purpose
Manage users, permissions, and sessions for the dashboard system.

## Functional Requirements
1. Support login/logout
2. Manage roles, such as admin and viewer
3. Protect important endpoints with authentication
4. Store audit logs for important actions

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
- [ ] Important endpoints require authentication
- [ ] Roles can restrict actions
- [ ] Audit logs exist for start/stop/live actions

## Priority
MVP Core
