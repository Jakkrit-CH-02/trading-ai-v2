# Project Structure (Reference)

โครงสร้างโปรเจกต์จริงที่จะใช้ ตอน scaffold คุณไม่ต้องสร้างทุกโฟลเดอร์ทีเดียว — สร้างเฉพาะที่ slice แรกต้องการ แล้วค่อยขยาย

## Repo top-level

```
trading-ai-v2/
├── trading_bot_requirements_v2/        # requirement docs (existing) — read-only ในมุมมอง code
└── app/                                # โปรเจกต์จริง (สร้างใหม่)
    ├── CLAUDE.md                       # มาจาก _flow/CLAUDE.md
    ├── README.md
    ├── .env.example
    ├── .gitignore
    ├── docker-compose.yml              # postgres + redis + 3 services for dev
    ├── Makefile                        # ปุ่มเดียวสำหรับงานบ่อยๆ
    ├── .claude/
    │   └── commands/                   # slash commands (จาก _flow/commands/)
    └── apps/
        ├── frontend/                   # ดู frontend.CLAUDE.md
        ├── backend-go/                 # ดู backend-go.CLAUDE.md
        └── ai-python/                  # ดู ai-python.CLAUDE.md
```

## Why a monorepo

- Strategy/risk types ต้อง match กันระหว่าง Go backend ↔ Python AI ↔ Frontend types — อยู่ที่เดียวจะ refactor ง่าย
- Slice แรกแตะ 2 service พร้อมกัน (Go + Frontend) — ไม่ต้องเปิด 2 repo
- ใช้ pnpm workspaces (frontend), Go module เดี่ยว (backend), uv (AI) แต่ละอันแยก dep ได้ ไม่ชนกัน

## Top-level Makefile (ตัวอย่าง)

```make
.PHONY: dev test lint up down

up:
	docker compose up -d postgres redis

down:
	docker compose down

dev-fe:
	pnpm --filter frontend dev

dev-be:
	cd apps/backend-go && go run ./cmd/api

dev-ai:
	cd apps/ai-python && uv run uvicorn ai.main:app --reload --port 8001

test:
	pnpm --filter frontend test:ci
	cd apps/backend-go && go test ./...
	cd apps/ai-python && uv run pytest

lint:
	pnpm --filter frontend lint
	cd apps/backend-go && golangci-lint run
	cd apps/ai-python && uv run ruff check src tests
```

## docker-compose.yml (เฉพาะ infra สำหรับ dev)

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: tradingbot
      POSTGRES_USER: bot
      POSTGRES_PASSWORD: bot
    ports: ["5432:5432"]
    volumes: [pgdata:/var/lib/postgresql/data]
  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
volumes:
  pgdata:
```

Backend/Frontend/AI **รันบนเครื่องตรงๆ** ระหว่าง dev (เร็วกว่ามาก เวลา debug) Docker ใช้แค่ Postgres+Redis

## Frontend folder (สรุป — รายละเอียดดู `frontend.CLAUDE.md`)

```
apps/frontend/
├── CLAUDE.md
├── package.json
├── vite.config.ts
├── tsconfig.json
└── src/
    ├── main.tsx
    ├── App.tsx
    ├── routes.tsx
    ├── theme.ts
    ├── lib/         # api, ws, format
    ├── pages/       # 1 folder ต่อ 1 requirement screen
    ├── components/  # cross-page
    ├── stores/      # Zustand
    ├── api/         # axios + zod ต่อ backend domain
    ├── types/
    └── test/
```

## Backend Go folder (สรุป — รายละเอียดดู `backend-go.CLAUDE.md`)

```
apps/backend-go/
├── CLAUDE.md
├── go.mod
├── cmd/
│   ├── api/        # HTTP API
│   ├── bot/        # bot runtime
│   └── migrate/
├── internal/
│   ├── auth/       binance/    data/
│   ├── strategy/   risk/       order/
│   ├── paper/      backtest/   tradelog/
│   ├── runtime/    alert/      api/
│   ├── ai/         platform/   domain/
├── config/
├── migrations/
└── test/
```

## AI Python folder (สรุป — รายละเอียดดู `ai-python.CLAUDE.md`)

```
apps/ai-python/
├── CLAUDE.md
├── pyproject.toml
├── uv.lock
├── src/ai/
│   ├── main.py     config.py    logging.py
│   ├── api/        dataset/     features/
│   ├── training/   registry/    inference/
│   ├── evaluation/ explain/     domain/
├── tests/
└── models/         # gitignored
```

## Order of scaffolding (สำหรับ slice แรก)

ไม่ต้องสร้างทุกอย่าง ตอน `VERTICAL_SLICE_1` ต้องการแค่:

1. `app/CLAUDE.md`
2. `app/docker-compose.yml` + `Makefile`
3. `apps/backend-go/` (เฉพาะ packages ที่ slice ต้องการ: `binance/`, `data/`, `strategy/`, `risk/`, `order/`, `paper/`, `runtime/`, `tradelog/`, `api/`, `platform/`, `domain/`)
4. `apps/frontend/` (เฉพาะ pages: `dashboard/`, `bot-control/`)
5. `apps/ai-python/` — ยังไม่แตะใน slice 1

ขยายอย่างอื่นเมื่อ slice ถัดไปต้องการจริง ไม่ scaffold ล่วงหน้า
