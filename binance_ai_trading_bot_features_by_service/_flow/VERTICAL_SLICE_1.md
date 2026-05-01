# Vertical Slice 1 — Paper Trade BTC/USDT MA Crossover

> **Goal:** กดปุ่ม Start ใน Frontend → Backend สั่ง paper trade BTC/USDT บน Binance testnet ด้วย MA cross 9/21 ที่ 1m timeframe → เห็น order + P&L ใน Dashboard
> **No AI service ใน slice นี้** (เริ่ม Phase 4 ทีหลัง)

## Definition of Done (verify ผ่านแล้วถึงปิด slice)

1. ☐ Backend เชื่อม Binance testnet ได้ (REST + WS)
2. ☐ Strategy `ma_cross` รัน OnBar() บน 1m candle ผลิต Signal ถูกต้อง (มี unit test)
3. ☐ Risk engine reject signal ที่ขัด policy (มี unit test)
4. ☐ Paper engine รับ ValidatedSignal แล้ว simulate fill ตามราคา + log
5. ☐ Frontend Bot Control ส่ง Start command, Dashboard แสดง P&L + open positions แบบ real-time (poll 2s OK ใน slice นี้)
6. ☐ ปิด process ด้วย Ctrl+C ไม่มี panic, no leaked goroutine
7. ☐ รันต่อเนื่อง 30 นาทีบน testnet ไม่ crash
8. ☐ `make test` ทุกอันผ่าน

## ขอบเขต (สิ่งที่อยู่ใน slice นี้)

| Layer | สิ่งที่ต้องทำ |
|---|---|
| Frontend | `dashboard/`, `bot-control/` 2 หน้า + axios + Query setup + theme |
| Backend Go | `binance/`, `data/`, `strategy/` (เฉพาะ ma_cross), `risk/` (เฉพาะ position size + stop loss required), `order/`, `paper/`, `runtime/`, `tradelog/`, `api/` (เฉพาะ /api/bot/* + /api/dashboard/*) |
| Backend infra | Postgres + Redis ผ่าน docker-compose |
| AI Python | **ยังไม่แตะ** |
| Auth | **ยังไม่ทำ** — single-user mode, hardcoded `Authorization: Bearer dev` |
| Live trading | **ปิดสนิท** — `LIVE_TRADING_ENABLED=false` ใน .env |

## ลำดับ prompt ที่จะให้ Claude ทำ (ทำตามลำดับ อย่ารวบ)

แต่ละ step คือ 1 prompt 1 commit

### Step 0 — Scaffold (1 prompt)
```
ตาม STRUCTURE.md และ CLAUDE.md
สร้างโครง app/ ใหม่ที่ /Users/teng/personal/app/trading-ai-v2/app/ ด้วย:
- root CLAUDE.md (copy จาก _flow/CLAUDE.md)
- docker-compose.yml (postgres + redis)
- Makefile
- apps/backend-go/ (go.mod + cmd/api/main.go ที่รัน chi server เปล่าๆ + apps/backend-go/CLAUDE.md)
- apps/frontend/ (vite + react-ts template + apps/frontend/CLAUDE.md)
- apps/ai-python/ ยังไม่ต้องสร้าง

หลังเสร็จ verify: `cd apps/backend-go && go run ./cmd/api` ต้องเปิด port 8080 ได้, `cd apps/frontend && pnpm dev` ต้องเปิด port 5173 ได้
```

### Step 1 — Domain types + platform helpers (Backend)
```
อ่าน apps/backend-go/CLAUDE.md
สร้าง:
- internal/domain/{symbol,bar,order,position,mode,signal}.go
- internal/platform/timex/timex.go (NowMs, MsToTime)
- internal/platform/ids/ids.go (ULID)
- internal/platform/decimalx/decimalx.go (helper compare/format)
- internal/platform/config/config.go (viper loader, RiskConfig + BinanceConfig)
- config/config.dev.yaml (testnet keys placeholder, risk defaults)

ทุก type ต้องมี go doc บรรทัดเดียว ไม่ต้องเขียนยาว
```

### Step 2 — Binance connector (testnet)
```
อ่าน ../trading_bot_requirements_v2/backend-go/02_binance_connector.md และ apps/backend-go/CLAUDE.md
implement internal/binance/:
- rest.go: Client struct, methods GetExchangeInfo, GetAccount, PlaceOrder, CancelOrder, GetKlines
- ws.go: KlineStream(symbol, interval) returns <-chan domain.Bar
- ratelimit.go: token bucket
- testnet config switch
- รองรับ reconnect (exponential backoff)

unit test: mock httptest server สำหรับ rest.go, จำลอง disconnect สำหรับ ws.go
```

### Step 3 — Data collector + market data service
```
อ่าน req 03_data_collector + 04_market_data_service
internal/data/:
- collector.go: subscribe ws, store to redis (latest bars per symbol/timeframe)
- store.go: postgres schema bar_history + write batch
- candles.go: read API for strategy/backtest

migration 0001_init.sql: tables bar_history, trade_log
```

### Step 4 — Strategy engine + ma_cross
```
อ่าน req 05_strategy_engine
internal/strategy/:
- types.go: Signal, Reason, RuleConfig
- engine.go: Engine struct, Engine.OnBar(bar) Signal
- registry.go: name -> constructor
- builtin/ma_cross.go: stateful tracker (last fast EMA, last slow EMA)

unit test แบบ table-driven: 5 cases (warmup, no-cross, cross-up, cross-down, ดูแลให้ EMA recompute ถูกต้อง)
ใช้ data fixture ใน test/fixtures/btcusdt_1m_sample.csv (~200 bars)
```

### Step 5 — Risk engine (subset for slice 1)
```
อ่าน req 06_risk_engine และ root CLAUDE.md (risk policy section)
internal/risk/:
- types.go: ValidatedSignal, ErrPositionTooLarge, ErrStopLossRequired
- policy.go: Policy struct loaded from config
- checks.go: Engine.Validate(signal, equity, openPositions) -> ValidatedSignal | error
- เฉพาะ check 1 (position size) + check 3 (stop loss required) ใน slice นี้

เขียน checks_test.go ก่อน implementation (test-as-spec)
ครอบคลุม: oversized signal reject, missing stop reject, valid signal pass
```

### Step 6 — Order manager + paper engine
```
อ่าน req 07_order_manager + 08_paper_trading_engine
internal/order/:
- manager.go: Manager.Submit(ctx, ValidatedSignal) -> Order
- router.go: route based on mode (paper vs live; live ปิดใน slice นี้)
internal/paper/:
- engine.go: simulate fill ที่ราคา bar.Close + spread ค่าคงที่ 1bp
- maintain virtual balance, open positions, P&L
- emit TradeLog event

integration test: ส่ง 5 signals หลายแบบ ตรวจ balance + P&L ตอนจบ
```

### Step 7 — Trade log service
```
อ่าน req 10_trade_log_service
internal/tradelog/:
- service.go: Record(trade) -> error, List(filter) -> []TradeLog
- เขียนลง postgres table trade_log
- ดึง P&L summary สำหรับ dashboard (today, all-time)
```

### Step 8 — Runtime controller + pipeline
```
อ่าน req 11_bot_runtime_controller
internal/runtime/:
- state.go: FSM (idle, running, paused, halted)
- controller.go: Start/Stop/Pause/Kill methods
- pipeline.go: เชื่อม data -> strategy -> risk -> order -> tradelog
- graceful shutdown รับ SIGINT

ทดสอบ manual: รัน cmd/bot กด Ctrl+C ต้องปิด clean ภายใน 5 วินาที
```

### Step 9 — API gateway routes (subset)
```
อ่าน req 13_api_gateway
internal/api/:
- server.go: chi setup, middleware (recover, request_id, slog, hardcoded auth=dev)
- handlers/bot.go: POST /api/bot/start, /stop, /pause; GET /api/bot/status
- handlers/dashboard.go: GET /api/dashboard/summary (equity, P&L, open positions)
- handlers/strategies.go: GET /api/strategies (list available + active)
- ws.go: ยังไม่ต้องทำใน slice นี้ (poll พอ)

ตอบ JSON shape { data, error } ตามที่ระบุใน CLAUDE.md
integration test: บูตจริง + http call แต่ละ endpoint
```

### Step 10 — Frontend scaffold + theme + lib
```
อ่าน apps/frontend/CLAUDE.md
ทำ:
- src/theme.ts (dark theme, primary green ที่อ่านได้, money font monospace)
- src/lib/api.ts (axios + base URL จาก env, hardcoded Bearer dev header)
- src/lib/queryClient.ts
- src/lib/format.ts (formatMoney, formatPct, formatTime)
- src/App.tsx (router shell + AppShell with sidebar)
- src/routes.tsx (2 routes: /, /bot)

ยังไม่ต้องทำหน้าจริง แค่ shell + 2 placeholder
```

### Step 11 — Dashboard page
```
อ่าน req 01_dashboard
src/pages/dashboard/:
- DashboardPage.tsx: 4 KPI cards (equity, today P&L, open positions, bot state)
- components/KpiCard.tsx
- components/OpenPositionsTable.tsx
- hooks/useDashboard.ts (useQuery refetchInterval 2000)

api: src/api/dashboard.ts ด้วย zod schema
sx prop only ตาม frontend.CLAUDE.md
```

### Step 12 — Bot Control page (the start button)
```
อ่าน req 03_bot_control
src/pages/bot-control/:
- BotControlPage.tsx
- components/ModeSelector.tsx (radio: backtest/paper/live; live disabled พร้อม tooltip "live disabled in dev")
- components/StrategyPicker.tsx (select: ma_cross_btcusdt)
- components/SymbolTimeframePicker.tsx (BTCUSDT, 1m)
- components/RiskFormFields.tsx (max position %, stop loss %)
- hooks/useBotControl.ts

react-hook-form + zod, ปุ่ม Start ส่ง POST /api/bot/start
แสดง runtime status จาก useQuery
ถ้า backend reject แสดง error toast (rely on global onError)
```

### Step 13 — End-to-end smoke test
```
รัน:
1. make up (postgres + redis)
2. cd apps/backend-go && go run ./cmd/migrate up
3. cd apps/backend-go && go run ./cmd/api  (terminal 1)
4. cd apps/backend-go && go run ./cmd/bot  (terminal 2)
5. cd apps/frontend && pnpm dev (terminal 3)
6. เปิด http://localhost:5173
7. ไป /bot → เลือก paper, ma_cross, BTCUSDT, 1m → Start
8. กลับ / (Dashboard) → เห็น state = running, equity, รอ ~5 นาที เห็น candle bar updates

acceptance: รันต่อเนื่อง 30 นาที ไม่ crash, ถ้ามี cross เกิดขึ้น เห็น trade ใน OpenPositionsTable
```

---

## หลัง slice นี้เสร็จ (next slice candidates)

- **Slice 2** — Backtest engine + frontend backtest page (ใช้ strategy + risk เดิม)
- **Slice 3** — Trade Logs page + WebSocket push (เลิก poll)
- **Slice 4** — Risk Monitor page + drawdown halt logic (check 2 + 4)
- **Slice 5** — เพิ่ม strategy ที่ 2 (RSI+EMA) + StrategyPicker หลายอัน
- **Slice 6** — เริ่ม AI service: dataset builder + feature pipeline (ยังไม่เชื่อม backend)
- **Slice 7** — เชื่อม AI inference เข้า strategy engine
- **Slice 8** — Alerts + Settings + multi-user auth
- **Slice 9** — Live trading gate (ทุก check 1-5 + kill switch)

---

## ข้อควรระวังสำหรับ slice นี้โดยเฉพาะ

- **Binance testnet API key** ต้องมีก่อน — สมัครที่ testnet.binance.vision
- **Decimal serialization** — ตรวจให้แน่ใจว่า zod ใน frontend parse string number ได้
- **WebSocket reconnect** — ทดสอบโดยตัด wifi 30 วินาที
- **Time skew** — Binance reject order ถ้า `recvWindow` กับ `serverTime` ห่างกันเกิน — sync time helper ใน binance/rest.go
- **Goroutine leak** — ทุก goroutine ใน pipeline ต้องรับ `<-ctx.Done()` ทดสอบด้วย `go test -run TestRuntimeShutdown -race`
