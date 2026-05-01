.PHONY: up down dev-fe dev-be dev-ai test lint tidy migrate

up:
	docker compose up -d postgres redis

down:
	docker compose down

dev-fe:
	pnpm --dir apps/frontend dev

dev-be:
	cd apps/backend && go run ./cmd/api

dev-bot:
	cd apps/backend && go run ./cmd/bot

dev-ai:
	cd apps/ai-service && uv run uvicorn ai.main:app --reload --port 8001

test:
	pnpm --dir apps/frontend test:ci || true
	cd apps/backend && go test ./...

lint:
	pnpm --dir apps/frontend lint || true
	cd apps/backend && golangci-lint run || true

tidy:
	cd apps/backend && go mod tidy

migrate:
	@if [ -d apps/backend/migrations ] && ls apps/backend/migrations/*.sql >/dev/null 2>&1; then \
		cd apps/backend && goose -dir migrations postgres "$$DATABASE_URL" up; \
	else \
		echo "No migrations found in apps/backend/migrations — nothing to do."; \
	fi
