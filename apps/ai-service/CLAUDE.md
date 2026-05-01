# AI Service (Python)

> Read with root `/CLAUDE.md`. This file = Python-only rules.

## Tech

- Python 3.11+ (use `match`, PEP 604 unions, `typing.Self`)
- HTTP: FastAPI + `uvicorn[standard]`
- Validation: pydantic v2 (+ pydantic-settings for config)
- Data: pandas, polars, numpy
- ML: scikit-learn, joblib (model persistence)
- HTTP client: httpx (async)
- Package manager: `uv` only — no pip/poetry/pipenv
- Lint/format: `ruff` (when added). Type-check: `mypy --strict` on `app/`.

## Module layout

```
apps/ai-service/
├── CLAUDE.md
├── pyproject.toml
├── Dockerfile
├── app/
│   ├── main.py            # FastAPI app + lifespan
│   ├── core/
│   │   ├── config.py      # Settings (pydantic-settings, AI_ env prefix)
│   │   └── logging.py     # JSON structured logging
│   ├── api/               # routers, one file per requirement
│   ├── domain/            # pydantic models shared across packages
│   ├── features/          # feature engineering (pure functions)
│   ├── datasets/          # dataset assembly from backend bars
│   ├── models/            # train / predict wrappers
│   ├── registry/          # model registry (load/save via joblib)
│   └── clients/
│       └── backend.py     # httpx client to Go backend (the ONLY data source)
└── tests/
```

**Mapping rule:** each `trading_bot_requirements_v2/ai-python/NN_*.md` → exactly one `app/<domain>/` package. Do not collapse.

## Hard rules

- **Never call Binance.** Period. All market bars come from the Go backend over HTTP (`app/clients/backend.py`). Binance SDKs must not appear in `pyproject.toml`.
- **Money** — never `float`. Use `decimal.Decimal`. JSON transport as string ("0.00012345"). pydantic field type: `Decimal` with `model_config = ConfigDict(json_encoders={Decimal: str})` (or a typed `Annotated` alias).
- **Time** — UTC, `int64` Unix milliseconds across HTTP. Convert to `datetime` only inside compute paths.
- **IDs** — ULID, lowercase, producer-generated.
- **Stateless service.** No in-process mutable globals beyond config and the model registry cache. Long-lived state belongs in the Go backend / Postgres.

## Conventions

### Config

- All settings in `app/core/config.py` via `pydantic-settings`
- Env prefix: `AI_` (e.g. `AI_BACKEND_BASE_URL`)
- Loaded once via `get_settings()` (lru_cache); inject via FastAPI `Depends` — never read env in business code.

### Logging

```python
import logging
log = logging.getLogger(__name__)

log.info(
    "inference complete",
    extra={"mode": mode, "symbol": symbol, "request_id": rid, "model_id": mid},
)
```

- JSON formatter (see `app/core/logging.py`)
- Required keys: `service`, `mode`, `symbol` (when applicable), `request_id`
- No `print()`. No bare `logging.info(...)` without `extra=` for context fields.

### Errors

- Raise typed exceptions; FastAPI exception handlers map to:
  `{ "data": null, "error": { "code": "...", "message": "..." } }`
- Stable error codes: `validation_failed`, `not_found`, `upstream_unavailable`, `model_unavailable`
- Never swallow — re-raise or log at `error` with full context.

### HTTP API

- Routers in `app/api/`, one file per requirement
- Response envelope matches Go backend: `{ "data": ..., "error": null }` or error variant
- Request/response models are pydantic v2; never expose internal dataclasses directly
- All I/O endpoints `async def`; CPU-bound work goes through `run_in_executor` or a worker

### Backend client

- Single `httpx.AsyncClient` reused via FastAPI lifespan
- Timeout from `Settings.backend_timeout_s`
- Retries with exponential backoff for 5xx only; never retry 4xx
- All bar fetches go through `app/clients/backend.py` — no other module makes HTTP calls outbound for market data

## Testing

- `pytest` + `pytest-asyncio` (when added)
- Unit tests for `features/` and `models/` (pure → heavy coverage)
- Integration tests use httpx `MockTransport` for the backend client; never hit the real backend in unit tests
- Coverage target: 85% on `features/` and `models/`

## Build & run

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001
uv run pytest
```

## Don'ts

- No Binance SDK / direct Binance HTTP / Binance WS — anywhere
- No `float` for prices, qty, equity, P&L
- No `print` — use `logging` with `extra=`
- No global mutable state outside `app/core/` and the model registry
- No synchronous blocking I/O inside `async def` handlers
- No reading `os.environ` outside `app/core/config.py`
- No third programming language; no JS/TS in this service
