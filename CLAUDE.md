# Softtrade — AI Trading Bot สำหรับ Binance

สเปกฉบับเต็มอยู่ที่ `docs/SPEC.md` อ่านหัวข้อที่เกี่ยวข้องทุกครั้งก่อนเริ่มงาน และใช้ `design/Neumorphic_Trading_Dashboard.pdf` เป็นต้นแบบ UI (ค่าสีให้ใช้ตามตาราง 9.1 ใน SPEC.md ไม่ต้องดูดสีจาก PDF)

## หลักการที่ห้ามละเมิด
1. **Risk first** — ทุกคำสั่งซื้อขายต้องผ่าน Risk Engine ไม่มีทางลัด รวมถึงคำสั่งจาก AI และคำสั่ง manual
2. **Same code everywhere** — กลยุทธ์เป็น pure function (candles + state → Signal) ใช้โค้ดเดียวกันทั้ง backtest, paper, live ผ่าน `ExchangeAdapter`
3. **Exchange-side stops** — วาง stop-loss บน Binance ทันทีหลัง fill ถ้าวางไม่ได้ใน 3 วินาที ให้ปิดสถานะ
4. **Fail safe** — ข้อมูลค้าง, API error, rate limit → หยุดเปิดออเดอร์ใหม่ แต่ยังดูแลสถานะเดิม
5. **Explainable** — บันทึกเหตุผลทุกการตัดสินใจ (signals, risk_events, ai_analyses, audit_log)

## Stack
- Backend: Python ล้วน (3.12+, uv, FastAPI, SQLAlchemy 2 async, Alembic, Redis, PostgreSQL + TimescaleDB)
- Frontend: React + TypeScript + Vite, Tailwind CSS v4, Radix/shadcn, TradingView Lightweight Charts, TanStack Query, Zustand
- AI: Anthropic SDK (claude-haiku-5-5 จัดหมวดข่าว, claude-sonnet-5-5 วิเคราะห์), LightGBM

## กฎการทำงาน
- ทำทีละ Phase ตาม SPEC.md หัวข้อ 13 วางแผนก่อนแล้วรอให้อนุมัติ
- เงินใช้ `Decimal` / `NUMERIC(28,10)` เท่านั้น ห้ามใช้ float, เวลาเป็น UTC
- ห้าม commit secret, ห้าม log API key/secret/signature, ห้ามส่ง key ให้ LLM
- ก่อน Phase 7 ผ่าน Gate B ใช้ได้เฉพาะ Binance Testnet / Demo
- Risk Engine ต้องมี test coverage ≥ 95%
- จบงานทุกครั้ง: รัน lint + test ทั้งหมด แล้วสรุปสิ่งที่เปลี่ยน

## คำสั่ง
- `cp .env.example .env && docker compose up -d` (api: http://localhost:8000/health, web: http://localhost:5173)
- Backend: `cd backend && uv run pytest` · `uv run ruff check . && uv run mypy`
- Frontend: `cd frontend && npm run dev` · `npm run lint && npm test` · ดู component ที่ `/dev/ui` · `npm run gen:api` สร้าง `src/lib/api-types.ts` ใหม่จาก OpenAPI ของ backend (รันทุกครั้งที่แก้ schema)
- API: `cd backend && uv run uvicorn app.main:app --port 8000` (ต้องตั้ง `DATABASE_URL` ของ DB ที่มี candles ใน `.env`; ไม่มี key Demo = Dashboard แสดง "ยังไม่ได้เชื่อมบัญชี")
- Migration: `cd backend && uv run alembic revision --autogenerate -m "..."` · `uv run alembic upgrade head`
- Backfill: `cd backend && uv run softtrade backfill --symbols BTCUSDT --intervals 1h 4h --days 30` (ข้อมูล public ไม่ต้องมี key; รันซ้ำได้)
- Backtest: `cd backend && uv run softtrade backtest --strategy s1 --symbol BTCUSDT --years 3` · เพิ่ม `--walk-forward --grid tp1_r=1.2,1.5` เพื่อดูผล out-of-sample · `--symbols BTCUSDT ETHUSDT SOLUSDT BNBUSDT XRPUSDT` รวมหลายเหรียญเป็นพอร์ตถ่วงน้ำหนักเท่ากัน (ต้อง backfill ก่อน และข้อมูล < 3 ปีจะไม่ผ่าน gate 1)
- Testnet: `cd backend && uv run softtrade testnet-check --stage 1` (1 อ่านอย่างเดียว · 2 +ออเดอร์ทดสอบ · 3 +OrderManager) ใช้ `BINANCE_API_KEY/SECRET` จาก `.env` และเลือกระบบด้วย `BINANCE_TRADING_ENV=demo` (Binance Demo Trading, demo-api.binance.com — ค่าเริ่มต้น) หรือ `testnet` (testnet.binance.vision) key ใช้ได้เฉพาะระบบที่สร้างมา; adapter ปฏิเสธทุก host อื่นรวมถึง api.binance.com
- Login: `cd backend && uv run softtrade gen-master-key` (ใส่ `MASTER_KEY` ใน `.env`, `JWT_SECRET` ≥ 32 ตัว) แล้ว `uv run softtrade create-user --email you@example.com` (ไม่มีหน้าสมัคร; พิมพ์ TOTP secret ให้ครั้งเดียว) · endpoint เสี่ยงต้องส่ง `X-TOTP`
- Risk Engine gate ใน CI: `uv run pytest tests/test_risk_*.py --cov=app.risk --cov-branch --cov-fail-under=95`
- Test ที่ใช้ DB จริง: ตั้ง `TEST_DATABASE_URL=postgresql+asyncpg://...` (ไม่ตั้ง = ข้าม) DB นั้นถูก downgrade/upgrade ทุกครั้ง ห้ามชี้ไปที่ DB จริง
