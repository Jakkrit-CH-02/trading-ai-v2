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
- Frontend: `cd frontend && npm run dev` · `npm run lint && npm test`
- Migration: `cd backend && uv run alembic revision --autogenerate -m "..."`
