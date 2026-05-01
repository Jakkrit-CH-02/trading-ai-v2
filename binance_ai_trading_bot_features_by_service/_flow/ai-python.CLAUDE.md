# AI Service (Python)

> Read together with the root `/CLAUDE.md`. This file covers Python-only rules.

## Tech

- Python 3.11+
- Package manager: `uv` (fast, reproducible). Lockfile: `uv.lock`.
- API: FastAPI + uvicorn
- Validation: pydantic v2
- Data: pandas 2.x, numpy, pyarrow (parquet IO)
- ML: scikit-learn for baseline classifiers, lightgbm for gradient boosting, optionally PyTorch later. **No TensorFlow.**
- Feature store: parquet files on disk for v1 (move to feast/redis later if needed)
- Logging: stdlib `logging` configured to JSON via `python-json-logger`
- Testing: `pytest`, `pytest-asyncio`
- Lint/format: `ruff` (lint + format)

## Folder layout

```
apps/ai-python/
├── CLAUDE.md
├── pyproject.toml
├── uv.lock
├── README.md
├── src/
│   └── ai/
│       ├── __init__.py
│       ├── main.py                  # FastAPI app entrypoint
│       ├── config.py                # pydantic settings, env loading
│       ├── logging.py               # JSON logger setup
│       │
│       ├── api/                     # req 06_inference_api + 07_signal_explanation
│       │   ├── __init__.py
│       │   ├── deps.py              # FastAPI dependencies
│       │   ├── routes_inference.py
│       │   ├── routes_explain.py
│       │   ├── routes_health.py
│       │   └── schemas.py           # request/response pydantic models
│       │
│       ├── dataset/                 # req 01_dataset_builder
│       │   ├── builder.py
│       │   ├── sources.py           # parquet readers, raw candle loaders
│       │   └── splits.py            # train/val/test, walk-forward
│       │
│       ├── features/                # req 02_feature_engineering
│       │   ├── pipeline.py          # FeaturePipeline class
│       │   ├── indicators.py        # rsi, ema, macd, atr, ...
│       │   ├── microstructure.py    # spread, depth-derived
│       │   └── normalize.py         # z-score, robust scaling
│       │
│       ├── training/                # req 03_training_pipeline
│       │   ├── trainer.py
│       │   ├── cv.py                # walk-forward CV
│       │   ├── metrics.py
│       │   └── runs.py              # run metadata, hash inputs
│       │
│       ├── registry/                # req 04_model_registry
│       │   ├── registry.py          # save/load models, list versions
│       │   ├── store.py             # filesystem layout: models/<name>/<version>/
│       │   └── manifest.py          # pydantic model for model metadata
│       │
│       ├── inference/               # the actual predict() path
│       │   ├── service.py           # InferenceService — load active model, predict
│       │   ├── fallback.py          # used when no model is active
│       │   └── cache.py             # short-TTL cache on identical input
│       │
│       ├── evaluation/              # req 05_backtest_ai_evaluation
│       │   ├── evaluator.py
│       │   └── reports.py
│       │
│       ├── explain/                 # req 07_signal_explanation
│       │   ├── shap_explainer.py
│       │   └── narrative.py         # human-readable signal reason
│       │
│       └── domain/                  # cross-module types
│           ├── __init__.py
│           ├── candles.py           # Bar pydantic model
│           ├── features.py          # FeatureVector
│           ├── signals.py           # Signal (BUY/SELL/HOLD), confidence, risk_score
│           └── mode.py              # Mode enum
│
├── tests/
│   ├── conftest.py
│   ├── test_inference_api.py
│   ├── test_features.py
│   ├── test_registry.py
│   └── fixtures/
│       └── sample_candles.parquet
└── models/                          # gitignored — runtime artifact
    └── README.md                    # explains layout
```

**Mapping rule:** each file in `../trading_bot_requirements_v2/ai-python/NN_*.md` corresponds to exactly one module under `src/ai/`. Keep boundaries clean.

## Module rules

- All public types are pydantic v2 `BaseModel`s; no untyped dicts crossing module boundaries
- Domain types live in `src/ai/domain/`. They depend on nothing in this project.
- Top-level imports only — no in-function `import` except for optional heavy deps (torch)
- Any module producing a model artifact must write through `registry/`, never directly to disk

## Inference API contract (the contract that matters)

The Go backend calls one main endpoint:

```
POST /ai/inference
Request:
{
  "request_id": "01HXYZ...",      // ULID, propagate to logs
  "symbol": "BTCUSDT",
  "timeframe": "1m",
  "as_of": 1730000000000,         // UTC ms
  "features": {                   // already-computed feature vector
    "rsi_14": 42.1,
    "ema_diff": 0.0023,
    ...
  },
  "model_name": "trend_v1",       // optional; default = active for symbol
  "mode": "paper"
}

Response:
{
  "request_id": "01HXYZ...",
  "signal": "BUY",                // BUY | SELL | HOLD
  "confidence": 0.74,             // 0..1
  "risk_score": 0.18,             // 0..1, higher = riskier
  "model_name": "trend_v1",
  "model_version": "2026-04-12_a3f",
  "latency_ms": 8,
  "fallback_used": false,
  "reason": "rsi oversold + ema reclaim"
}
```

- The schema is **stable** — adding fields is OK, removing or renaming is breaking
- `fallback_used: true` when no active model can serve the symbol (default = HOLD with confidence 0)
- Latency budget: p95 ≤ 50ms for 1m timeframe, ≤ 200ms for 5m+

## FastAPI patterns

```python
# routes_inference.py
from fastapi import APIRouter, Depends
from ai.api.schemas import InferenceRequest, InferenceResponse
from ai.api.deps import get_inference_service
from ai.inference.service import InferenceService

router = APIRouter(prefix="/ai", tags=["inference"])

@router.post("/inference", response_model=InferenceResponse)
async def infer(
    req: InferenceRequest,
    svc: InferenceService = Depends(get_inference_service),
) -> InferenceResponse:
    return await svc.predict(req)
```

- One router per route file
- Dependencies from `api/deps.py` — never instantiate services in route functions
- Request/response schemas in `api/schemas.py` (separate from domain models because they're transport contracts)
- `async def` for routes; if the work is CPU-bound, run in a threadpool via `await asyncio.to_thread(...)`

## Logging

```python
import logging
log = logging.getLogger(__name__)

log.info("inference served", extra={
    "service": "ai",
    "mode": req.mode,
    "symbol": req.symbol,
    "request_id": req.request_id,
    "model_version": resp.model_version,
    "latency_ms": resp.latency_ms,
    "fallback_used": resp.fallback_used,
})
```

- Use `extra=` for structured fields (matches root `CLAUDE.md` keys)
- One logger per module (`logging.getLogger(__name__)`), never the root logger
- No `print()` in `src/`. Tests may use `print` for debugging only.

## Model registry layout (filesystem v1)

```
models/
└── trend_v1/
    ├── active -> 2026-04-12_a3f          # symlink
    └── 2026-04-12_a3f/
        ├── model.joblib
        ├── feature_pipeline.joblib
        ├── manifest.json                 # ModelManifest schema
        ├── metrics.json                  # holdout metrics
        └── training_run.json             # hash of inputs, code git sha
```

- Promotion to "active" = atomic symlink swap
- The InferenceService loads the active model on startup and on a `SIGHUP` (or admin endpoint)
- Never load arbitrary user-uploaded files (security: pickle/joblib can execute code)

## Money & time

- All money values in `Decimal` (not float). Use `from decimal import Decimal`.
- Pydantic schemas: `Decimal` fields serialize as string in JSON
- Timestamps: `int` UTC ms, same as Go side. No `datetime` in transport.

## Testing

- pytest, fixtures in `conftest.py`
- Required tests:
  - `test_inference_api.py` — request/response schema stability, fallback behavior
  - `test_features.py` — at least one golden test per indicator (input candles → expected feature values)
  - `test_registry.py` — save/load roundtrip, version listing, active selection
- Run: `uv run pytest` (full) / `uv run pytest tests/test_features.py -k rsi` (focused)
- Use `pytest-asyncio` for FastAPI route tests via `httpx.AsyncClient`

## Build & run

```bash
uv sync
uv run uvicorn ai.main:app --reload --port 8001
uv run pytest
uv run ruff check src tests
uv run ruff format src tests
```

## Don'ts (Python-specific)

- No `float` for prices, qty, equity. Use `Decimal`.
- No untyped `dict[str, Any]` returned from public functions
- No global mutable state. The InferenceService instance is the only stateful object, owned by FastAPI lifespan.
- No `requests` library. Use `httpx` if you need an HTTP client (currently you don't — backend calls *us*).
- No notebook (`.ipynb`) committed. Experiments live elsewhere.
- No model file >100MB committed. Models go to object storage in production; for dev, gitignore `models/`.
- Do not call Binance from this service.
