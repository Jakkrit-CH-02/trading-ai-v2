# Binance AI Trading Bot (ภาษาไทย)

ระบบเทรดคริปโตอัตโนมัติสำหรับ Binance รองรับกลยุทธ์แบบ Rule-based และ AI พร้อม Risk Engine, โหมด Paper/Live/Backtest และหน้า UI สำหรับผู้ดูแลระบบ

## สถาปัตยกรรม

```
[Frontend (React/Vite/TS)]  ──HTTPS/WS──>  [Backend (Go)]  ──HTTP──>  [AI Service (Python)]
        :3000 / :5173                           :8080                        :8001
                                                  │
                                                  └──REST/WS──>  [Binance API]
```

| เซอร์วิส | เทคโนโลยี | หน้าที่ |
|-----------|-----------|---------|
| **Frontend** | React 18, Vite, TypeScript, MUI v5 | แดชบอร์ดผู้ดูแล, ควบคุมบอท, กราฟ, แจ้งเตือน |
| **Backend** | Go 1.22+, chi router, pgx, slog | ข้อมูลตลาด, กลยุทธ์, ความเสี่ยง, คำสั่งซื้อขาย, ยืนยันตัวตน, รันไทม์บอท |
| **AI Service** | Python 3.11+, FastAPI, scikit-learn | สร้างชุดข้อมูล, Feature Engineering, เทรนโมเดล, Inference |
| **PostgreSQL 16** | — | เทรด, แท่งเทียน, ผู้ใช้, การตั้งค่า, แจ้งเตือน, ล็อกตรวจสอบ |
| **Redis 7** | — | แคชข้อมูลตลาด, pub/sub |

Go Backend เป็นเซอร์วิส **เดียว** ที่เชื่อมต่อกับ Binance โดยตรง Frontend และ AI Service ไม่เรียก Binance โดยตรง

---

## โหมดการเทรด

| โหมด | คำอธิบาย | ความเสี่ยง |
|------|----------|-----------|
| **Backtest** | เล่นซ้ำแท่งเทียนในอดีตผ่านกลยุทธ์ ไม่มีเงินจริงหรือเงินจำลองที่เสี่ยง ใช้ประเมินผลกลยุทธ์ก่อนเทรดจริง | ไม่มี |
| **Paper** | เชื่อมต่อ Binance **testnet** WebSocket เพื่อรับราคาเรียลไทม์ แต่เทรดในพอร์ตจำลอง (simulated fills) ขั้นตอนเหมือนโหมด Live ทุกประการ | ไม่มี (เงินจำลอง) |
| **Live** | เชื่อมต่อ Binance **mainnet** และส่งคำสั่งซื้อขายจริง ต้องผ่านการตรวจสอบ 3 ขั้นตอน (ยืนยันผ่าน UI + env var + ตรวจสอบ API key) | เงินจริง |

---

## ฟีเจอร์แต่ละหน้า

### แดชบอร์ด (`/`)
- **สรุปพอร์ต** — ยอดคงเหลือ, equity, กำไร/ขาดทุนรายวัน, drawdown ปัจจุบัน
- **ตำแหน่งที่เปิดอยู่** — คู่เหรียญ, จำนวน, ราคาเฉลี่ยที่เข้า, ราคาปัจจุบัน, กำไร/ขาดทุนที่ยังไม่ปิด
- **สัญญาณ AI ล่าสุด** — คำสั่ง (buy/sell/hold), คะแนนความมั่นใจ, กลยุทธ์ที่สร้าง, เวลา
- **สถานะระบบ** — แสดงสถานะ Binance REST, Binance WS, AI service, ฐานข้อมูล และ Redis
- **แจ้งเตือนล่าสุด** — การแจ้งเตือนล่าสุดพร้อมระดับความรุนแรงและข้อความ

### Market Watch (`/market`)
- ราคาเรียลไทม์ของคู่เหรียญที่ติดตาม พร้อมกราฟ sparkline ขนาดเล็ก
- เปลี่ยนแปลงราคา 24 ชั่วโมง, ปริมาณ และ bid-ask spread
- อัปเดตราคาผ่าน Binance WebSocket

### ควบคุมบอท (`/bot`)
- **เลือกโหมด** — สลับระหว่าง backtest, paper และ live การเลือก live จะแสดงหน้าต่างยืนยัน
- **เลือกกลยุทธ์** — เลือกจาก `ma_cross` (moving average crossover), `rsi` หรือ `ai` (โมเดล ML)
- **คู่เหรียญ & ไทม์เฟรม** — เลือกคู่เทรด (เช่น BTCUSDT) และช่วงเวลาแท่งเทียน (1m, 5m, 15m, 1h ฯลฯ)
- **ตั้งค่าความเสี่ยง** — ปรับ max position size, daily drawdown limit, slippage cap และ stop-loss ต่อรอบ
- **ปุ่มควบคุม** — เริ่ม, หยุดชั่วคราว, กลับมาทำงาน, หยุด และ kill switch สถานะแสดงเป็น idle/running/paused/halted

### Paper Trading (`/paper`)
- พอร์ตจำลองพร้อมตั้งค่ายอดเงินเริ่มต้นได้
- ตารางตำแหน่งพร้อมมูลค่า mark-to-market และกำไร/ขาดทุนที่ยังไม่ปิด
- ประวัติเทรดทั้งหมดพร้อมฝั่ง, จำนวน, ราคา fill, ค่าธรรมเนียม และกำไร/ขาดทุนที่ปิดแล้ว
- กราฟ equity curve ติดตามมูลค่าพอร์ตตามเวลา
- ปุ่มรีเซ็ตเพื่อล้างตำแหน่งและเริ่มใหม่ด้วยเงินจำลอง

### บันทึกเทรด (`/logs`)
- ประวัติเทรดทั้งหมดทุกโหมด (paper, backtest, live)
- กรองได้ตามคู่เหรียญ, ช่วงวันที่, โหมด และฝั่ง (buy/sell)
- คอลัมน์: เวลา, คู่เหรียญ, ฝั่ง, จำนวน, ราคา fill, ค่าธรรมเนียม, กำไร/ขาดทุน, ยอดเงินหลังเทรด

### Risk Monitor (`/risk`)
- **Position exposure** — ขนาดตำแหน่งปัจจุบันเป็น % ของ equity เทียบกับค่าสูงสุดที่ตั้งไว้
- **Daily drawdown** — ขาดทุนรวม (ปิดแล้ว + ยังไม่ปิด) วันนี้ เทียบกับค่าสูงสุดที่ตั้งไว้
- **Slippage** — slippage ล่าสุดที่สังเกตได้ เทียบกับค่าสูงสุด (basis points)
- แบนเนอร์เตือนเมื่อเกินลิมิต บอทจะหยุดอัตโนมัติเมื่อ daily drawdown เกินค่าที่กำหนด

### Backtesting (`/backtest`)
- ตั้งค่า: คู่เหรียญ, ไทม์เฟรม, ช่วงวันที่, กลยุทธ์ และเงินเริ่มต้น
- ผลลัพธ์: total return, Sharpe ratio, max drawdown, win rate, profit factor
- รายการเทรดพร้อมราคาเข้า/ออก และกำไร/ขาดทุนต่อเทรด
- กราฟ equity curve
- เมตริก AI (accuracy, precision, recall) เมื่อใช้กลยุทธ์ AI

### AI Training (`/ai`)
- **สร้างชุดข้อมูล** — เลือกคู่เหรียญ, ไทม์เฟรม, ช่วงวันที่ และประเภท label (ทิศทางแท่งเทียนถัดไป, ผลตอบแทนอนาคต หรือ threshold)
- **คำนวณ features** — รัน feature engineering (RSI, EMA, MACD, volume ratio, volatility, trend strength)
- **เทรนโมเดล** — เลือกประเภทโมเดล (random forest, logistic regression, XGBoost, LightGBM) ตั้ง hyperparameters และเริ่มเทรน
- **Model registry** — ดูโมเดลทั้งหมดพร้อมเวอร์ชัน, เมตริก (accuracy, precision, recall, F1, AUC) และ promote โมเดลเป็น "active" สำหรับ inference
- **ทำนาย / อธิบาย** — ส่ง features ไปยังโมเดลที่ active และดูสัญญาณ, ความมั่นใจ, risk score และ feature importance

### แจ้งเตือน (`/alerts`)
- ประเภท: `drawdown_breach`, `order_rejection`, `binance_disconnect`, `slippage_exceeded`, `kill_triggered`
- ระดับ: info, warning, critical
- อ่านแล้วทีละรายการหรือทั้งหมด

### การตั้งค่า (`/settings`)
- สถานะ Binance API key (testnet vs mainnet, สิทธิ์ของ key)
- ฟอร์มตั้งค่าความเสี่ยง (max position %, max daily drawdown %, max slippage bps, บังคับ stop loss)
- ตั้งค่าการแจ้งเตือน (เลือกระดับความรุนแรงที่จะแจ้งเตือน)

---

## Risk Engine

ทุกคำสั่งซื้อขายในทุกโหมด (backtest, paper, live) ต้องผ่านการตรวจสอบเหล่านี้ก่อนดำเนินการ การละเมิดจะเป็น error ไม่ใช่แค่ warning

| กฎ | ค่าเริ่มต้น | การทำงาน |
|----|-----------|----------|
| **Position sizing** | 2% ของ equity | ปฏิเสธคำสั่งที่มูลค่า notional เกิน % ที่กำหนดของ equity |
| **Daily drawdown** | 5% ของ equity | หยุดบอทถ้าขาดทุนรวม (ปิดแล้ว + ยังไม่ปิด) ของวันเกินค่าที่กำหนด |
| **Stop-loss required** | เปิดใช้งาน | ทุกคำสั่งต้องมีราคา stop-loss คำสั่งที่ไม่มีจะถูกปฏิเสธ |
| **Slippage check** | 30 bps | คำสั่ง market คำนวณ slippage จาก order-book depth คำสั่งที่เกินลิมิตจะถูกปฏิเสธ |
| **Live trading gate** | — | สลับไป live ต้อง: (1) ยืนยันผ่าน UI (2) ตั้ง `LIVE_TRADING_ENABLED=true` (3) ตรวจสอบ Binance API key ผ่าน ขาดข้อใดข้อหนึ่งจะถูกบล็อก |
| **Kill switch** | — | `POST /api/bot/kill` ยกเลิกคำสั่งทั้งหมด, ปิดทุกตำแหน่ง และห้ามเปิดตำแหน่งใหม่จนกว่าจะเปิดใช้งานอีกครั้ง |

---

## กลยุทธ์

| กลยุทธ์ | วิธีการทำงาน |
|---------|-------------|
| `ma_cross` | Moving average crossover สร้างสัญญาณ BUY เมื่อ fast MA ตัดขึ้นเหนือ slow MA, SELL เมื่อตัดลง |
| `rsi` | อิง RSI สร้าง BUY เมื่อ RSI ต่ำกว่า oversold threshold, SELL เมื่อสูงกว่า overbought threshold |
| `ai` | เรียก Python AI service สำหรับ inference โมเดล ML ที่ active จะส่งสัญญาณ (buy/sell/hold) พร้อมคะแนนความมั่นใจ ถ้าโมเดลใช้ไม่ได้จะ fallback เป็น HOLD |

Strategy engine ประเมินทุกกลยุทธ์ที่ตั้งค่าไว้ทุกครั้งที่มีแท่งเทียนเข้ามา สัญญาณที่ไม่ใช่ HOLD ตัวแรกจะถูกใช้ ถ้าทุกกลยุทธ์ส่ง HOLD จะไม่มีการดำเนินการ

---

## ขั้นตอนการเทรด

```
แท่งเทียนเข้ามา (WebSocket / ข้อมูลในอดีต)
       │
       ▼
  Strategy.OnBar(bar)  →  Signal { action, strength, reason }
       │
       ▼
  Risk.Validate(signal, equity, dailyPnL)  →  ValidatedSignal  หรือ  ปฏิเสธ + แจ้งเตือน
       │
       ▼
  OrderManager.Submit(validatedSignal)  →  Order { symbol, side, qty, price, stopPrice }
       │
       ▼
  Router ส่งไปยัง executor:
    ├── Paper  →  simulated fill (close ± 1bp spread)
    ├── Live   →  Binance REST API order
    └── Backtest  →  historical fill simulator
       │
       ▼
  TradeLog.Record(fill)  →  บันทึกลง PostgreSQL
```

---

## Backend API Endpoints

### Auth (สาธารณะ)
| Method | Path | คำอธิบาย |
|--------|------|----------|
| POST | `/api/auth/register` | ลงทะเบียนผู้ใช้ใหม่ |
| POST | `/api/auth/login` | เข้าสู่ระบบ รับ JWT |
| POST | `/api/auth/logout` | ออกจากระบบ |
| GET | `/api/auth/me` | โปรไฟล์ผู้ใช้ปัจจุบัน |

### ควบคุมบอท (ต้องยืนยันตัวตน)
| Method | Path | คำอธิบาย |
|--------|------|----------|
| POST | `/api/bot/start` | เริ่มบอทพร้อมโหมด, กลยุทธ์, คู่เหรียญ |
| POST | `/api/bot/stop` | หยุดบอทอย่างปลอดภัย |
| POST | `/api/bot/pause` | หยุดบอทชั่วคราว |
| POST | `/api/bot/resume` | กลับมาทำงานต่อ |
| POST | `/api/bot/kill` | Kill switch — ยกเลิกทั้งหมด, ปิดตำแหน่ง, หยุดบอท |
| GET | `/api/bot/status` | สถานะรันไทม์ (idle/running/paused/halted) |

### ข้อมูล & การเทรด
| Method | Path | คำอธิบาย |
|--------|------|----------|
| GET | `/api/settings` | ดูการตั้งค่าผู้ใช้ |
| PUT | `/api/settings` | อัปเดตการตั้งค่า |
| GET | `/api/alerts` | รายการแจ้งเตือน |
| POST | `/api/alerts/{id}/ack` | ยืนยันการอ่านแจ้งเตือน |

### AI Proxy (backend ส่งต่อไปยัง Python)
| Method | Path | คำอธิบาย |
|--------|------|----------|
| POST | `/api/ai/datasets/build` | สร้างชุดข้อมูลที่มี label จากแท่งเทียน |
| POST | `/api/ai/features/compute` | คำนวณ feature vectors |
| POST | `/api/ai/training/run` | เริ่มงานเทรนโมเดล |
| GET | `/api/ai/training/{id}` | สถานะงานเทรน |
| GET | `/api/ai/models` | รายการโมเดล + โมเดลที่ active |
| POST | `/api/ai/models/{id}/promote` | Promote โมเดลเป็น active |
| POST | `/api/ai/predict` | รับผลทำนาย |
| POST | `/api/ai/predict/reload` | โหลดโมเดล active ใหม่ |

### Health
| Method | Path | คำอธิบาย |
|--------|------|----------|
| GET | `/healthz` | สถานะ backend |
| GET | `/api/ai/healthz` | สถานะ AI service |

---

## รายละเอียด AI Service

### Inference Response

เมื่อโมเดลที่ active ได้รับคำขอทำนาย จะส่งกลับ:

| ฟิลด์ | ประเภท | คำอธิบาย |
|-------|--------|----------|
| `signal` | string | `BUY`, `SELL` หรือ `HOLD` |
| `confidence` | float | 0.0–1.0 ความมั่นใจของโมเดลในสัญญาณ |
| `risk_score` | float | 0.0–1.0 ระดับความเสี่ยงที่ประเมิน |
| `probabilities` | object | ความน่าจะเป็นแต่ละคลาส (`{"buy": 0.76, "sell": 0.12, "hold": 0.12}`) |
| `model_id` | string | ULID ของโมเดลที่สร้างผลทำนาย |
| `model_version` | int | เลขเวอร์ชันโมเดล |
| `reason` | string | คำอธิบายที่อ่านได้ (เช่น "EMA trend positive, RSI not overbought") |

ถ้าไม่มีโมเดลที่โหลดอยู่ เซอร์วิสจะส่ง `HOLD` พร้อม confidence 0.0 และ risk_score 1.0

### ประเภทโมเดลที่รองรับ
- **Random Forest** (scikit-learn) — ค่าเริ่มต้น เป็น baseline ที่ดี
- **Logistic Regression** — เร็ว ตีความได้ง่าย
- **XGBoost** — gradient boosting (dependency เสริม)
- **LightGBM** — gradient boosting (dependency เสริม)

### ชุด Feature
RSI (14-period), EMA (20, 50, 200), MACD, volume ratio, volatility, trend strength คำนวณจากแท่งเทียน OHLCV และบันทึกเป็นไฟล์ Parquet

---

## Database Schema

ไฟล์ migration 8 ไฟล์ใน `apps/backend/migrations/`:

| Migration | ตาราง | วัตถุประสงค์ |
|-----------|-------|-------------|
| `0001_init` | `schema_meta` | Metadata / ติดตามเฟส |
| `0002_bar_history` | `bars` | เก็บแท่งเทียน OHLCV พร้อม composite index บน (symbol, interval, open_time) |
| `0003_trade_log` | `trade_log` | เทรดทุกรายการ: โหมด, คู่เหรียญ, ฝั่ง, จำนวน, ราคา fill, ค่าธรรมเนียม, กำไร/ขาดทุน, ยอดเงินหลังเทรด |
| `0004_backtest_results` | ตาราง backtest | การตั้งค่าและผลลัพธ์การ backtest |
| `0005_users` | `users` | ยืนยันตัวตน: username, password hash, role (admin/operator/viewer) |
| `0006_settings` | ตารางการตั้งค่า | การตั้งค่าผู้ใช้, พารามิเตอร์ความเสี่ยง, ตั้งค่าแจ้งเตือน |
| `0007_alerts` | `alerts` | ประวัติแจ้งเตือนพร้อมประเภท, ระดับ, สถานะอ่าน |
| `0008_audit_log` | ตาราง audit | Audit trail สำหรับการดำเนินการที่สำคัญ |

---

## การตั้งค่า

### Backend (`apps/backend/config/config.dev.yaml`)

```yaml
env: dev
mode: paper

server:
  host: 0.0.0.0
  port: 8080

binance:
  base_url: https://testnet.binance.vision
  ws_url: wss://stream.testnet.binance.vision
  api_key: ""        # ตั้งผ่าน BOT_BINANCE_API_KEY env var
  api_secret: ""     # ตั้งผ่าน BOT_BINANCE_API_SECRET env var
  testnet: true

db:
  dsn: postgres://postgres:postgres@localhost:5432/trading?sslmode=disable
  max_conns: 10
  min_conns: 1
  conn_max_lifetime_sec: 1800

redis:
  addr: localhost:6379
  password: ""
  db: 0

risk:
  max_position_pct: "0.02"
  max_daily_drawdown_pct: "0.05"
  max_slippage_bps: 30
  require_stop_loss: true
```

ทุกฟิลด์สามารถ override ด้วย environment variables โดยใช้ prefix `BOT_` (เช่น `BOT_RISK_MAX_POSITION_PCT=0.03`)

### AI Service

ตั้งค่าผ่าน environment variables ด้วย prefix `AI_`:

| ตัวแปร | ค่าเริ่มต้น | คำอธิบาย |
|--------|-----------|----------|
| `AI_ENV` | `dev` | Environment |
| `AI_LOG_LEVEL` | `INFO` | ระดับ log |
| `AI_HOST` | `0.0.0.0` | Listen host |
| `AI_PORT` | `8001` | Listen port |
| `AI_BACKEND_BASE_URL` | `http://backend:8080` | URL ของ Go backend สำหรับดึงข้อมูลแท่งเทียน |
| `AI_BACKEND_TIMEOUT_S` | `10.0` | HTTP timeout สำหรับเรียก backend |

---

## สิ่งที่ต้องมีก่อนเริ่ม

1. **บัญชี Binance Testnet** — ลงทะเบียนที่ [testnet.binance.vision](https://testnet.binance.vision) เพื่อรับ API keys สำหรับ paper trading ไม่ต้องใช้ API keys สำหรับ backtesting
2. **บัญชี Binance Mainnet** (สำหรับ live trading เท่านั้น) — API keys mainnet ที่มีสิทธิ์ spot trading อย่าตั้ง `LIVE_TRADING_ENABLED=true` จนกว่าจะพร้อม
3. **Docker & Docker Compose** — สำหรับการติดตั้งแบบ container
4. **หรือ toolchains ในเครื่อง** — Go 1.22+, Python 3.11+ กับ uv, Node.js 18+ กับ pnpm, PostgreSQL 16, Redis 7

---

## เริ่มต้นใช้งาน

### Docker Compose (แนะนำ)

```bash
# Clone และเริ่มทุกเซอร์วิส
git clone <repo-url> && cd trading-ai-v2
docker compose up --build

# เซอร์วิส:
#   Frontend   → http://localhost:3000
#   Backend    → http://localhost:8080
#   AI Service → http://localhost:8001
#   PostgreSQL → localhost:5432
#   Redis      → localhost:6379
```

### พัฒนาในเครื่อง

```bash
# 1. เริ่ม infrastructure
docker compose up postgres redis

# 2. รัน database migrations
cd apps/backend
for f in migrations/*.sql; do
  psql -h localhost -U postgres -d trading -f "$f"
done

# 3. เริ่ม backend
go run ./cmd/api -config config/config.dev.yaml

# 4. เริ่ม AI service
cd apps/ai-service
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8001

# 5. เริ่ม frontend
cd apps/frontend
pnpm install
pnpm dev
# → http://localhost:5173
```

---

## Environment Variables อ้างอิง

### Backend

| ตัวแปร | ค่าเริ่มต้น | จำเป็น | คำอธิบาย |
|--------|-----------|--------|----------|
| `BOT_ENV` | `dev` | ไม่ | Environment (dev/staging/prod) |
| `BOT_MODE` | `paper` | ไม่ | โหมดเทรดเริ่มต้น |
| `BOT_SERVER_HOST` | `0.0.0.0` | ไม่ | HTTP listen host |
| `BOT_SERVER_PORT` | `8080` | ไม่ | HTTP listen port |
| `BOT_DB_DSN` | (ดู config) | ใช่ | PostgreSQL connection string |
| `BOT_REDIS_ADDR` | `localhost:6379` | ใช่ | Redis address |
| `BOT_AI_SERVICE_URL` | `http://ai-service:8001` | ใช่ | AI service URL |
| `BOT_BINANCE_API_KEY` | — | สำหรับ paper/live | Binance API key |
| `BOT_BINANCE_API_SECRET` | — | สำหรับ paper/live | Binance API secret |
| `BOT_BINANCE_TESTNET` | `true` | ไม่ | ใช้ Binance testnet |
| `BOT_RISK_MAX_POSITION_PCT` | `0.02` | ไม่ | ขนาดตำแหน่งสูงสุด (fraction) |
| `BOT_RISK_MAX_DAILY_DRAWDOWN_PCT` | `0.05` | ไม่ | Daily drawdown สูงสุด (fraction) |
| `BOT_RISK_MAX_SLIPPAGE_BPS` | `30` | ไม่ | Slippage สูงสุด (basis points) |
| `BOT_RISK_REQUIRE_STOP_LOSS` | `true` | ไม่ | บังคับ stop-loss ทุกคำสั่ง |
| `LIVE_TRADING_ENABLED` | `false` | สำหรับ live | ต้องเป็น `true` เพื่อเปิด live trading |

### AI Service

| ตัวแปร | ค่าเริ่มต้น | จำเป็น | คำอธิบาย |
|--------|-----------|--------|----------|
| `AI_ENV` | `dev` | ไม่ | Environment |
| `AI_LOG_LEVEL` | `INFO` | ไม่ | ระดับ log |
| `AI_HOST` | `0.0.0.0` | ไม่ | Listen host |
| `AI_PORT` | `8001` | ไม่ | Listen port |
| `AI_BACKEND_BASE_URL` | `http://backend:8080` | ใช่ | Backend URL สำหรับดึงข้อมูลแท่งเทียน |
| `AI_BACKEND_TIMEOUT_S` | `10.0` | ไม่ | Backend HTTP timeout (วินาที) |

---

## บทบาทผู้ใช้

| บทบาท | สิทธิ์ |
|-------|-------|
| **admin** | ควบคุมทั้งหมด: จัดการผู้ใช้, แก้ไขการตั้งค่า, ควบคุมบอท, ดูข้อมูลทั้งหมด |
| **operator** | ควบคุมบอท (เริ่ม/หยุด/หยุดชั่วคราว), ดูข้อมูล, ไม่สามารถแก้ไขการตั้งค่าระบบ |
| **viewer** | อ่านอย่างเดียว: ดูแดชบอร์ด, ตำแหน่ง, บันทึกเทรด และแจ้งเตือน |

---

## ข้อตกลงข้ามเซอร์วิส

| เรื่อง | ข้อตกลง |
|-------|---------|
| **เวลา** | UTC ทุกที่ `int64` Unix milliseconds ในการส่งข้อมูล เวลาท้องถิ่นเฉพาะที่ UI เท่านั้น |
| **เงิน** | ห้ามใช้ floating point Go: `decimal.Decimal` (shopspring) Python: `Decimal` ส่งเป็น string (`"0.00012345"`) |
| **IDs** | ULID, ตัวเล็ก, สร้างโดยเซอร์วิสที่ผลิต |
| **Logging** | Structured JSON คีย์ที่ต้องมี: `service`, `mode`, `symbol`, `request_id` |
| **Errors** | ห้ามกลืน ส่งกลับขึ้นไปตาม call stack หรือ log ที่ระดับ `error` พร้อมบริบทครบ |
| **Config** | ไฟล์ YAML ตรวจสอบตอนเริ่มต้น Environment variables override ค่าในไฟล์ ห้าม hardcode คู่เหรียญ, threshold หรือ API keys |

---

## สิ่งสำคัญที่ควรรู้

1. **โหมด Paper เป็นค่าเริ่มต้นที่ปลอดภัย** ระบบเริ่มต้นในโหมด paper พร้อมการเชื่อมต่อ testnet คุณไม่สามารถเทรดเงินจริงได้โดยไม่ตั้งใจเพราะต้องผ่าน 3 ด่านอิสระ

2. **Risk engine ไม่สามารถข้ามได้** ทุกคำสั่งในทุกโหมดต้องผ่านการตรวจสอบความเสี่ยงเหมือนกัน ไม่มีทางข้าม ถ้า risk engine ปฏิเสธคำสั่ง จะสร้างแจ้งเตือนและยกเลิกคำสั่ง

3. **Kill switch ทำงานทันที** `POST /api/bot/kill` ยกเลิกคำสั่งทั้งหมด ปิดทุกตำแหน่ง และหยุดบอท ใช้เมื่อมีปัญหาในการเทรด live

4. **AI เป็นตัวเลือกเสริม** ระบบทำงานได้ด้วยกลยุทธ์ rule-based (`ma_cross`, `rsi`) อย่างเดียว AI training, inference และ Python service จำเป็นเฉพาะเมื่อต้องการสัญญาณจาก ML

5. **ข้อมูลตลาดทั้งหมดผ่าน Go backend** AI service ไม่เรียก Binance โดยตรง แต่ขอข้อมูลแท่งเทียนจาก backend ซึ่งเป็นเจ้าของการเชื่อมต่อ Binance

6. **ความแม่นยำของทศนิยมสำคัญ** ราคาและจำนวนไม่เคยเก็บหรือคำนวณเป็นเลขทศนิยมลอยตัว (floating-point) ระบบใช้ arbitrary-precision decimals ตลอด

7. **Backtest ก่อน paper, paper ก่อน live** ขั้นตอนที่แนะนำ: backtest กลยุทธ์ด้วยข้อมูลในอดีต จากนั้นรันในโหมด paper ด้วยราคาเรียลไทม์ แล้วค่อยพิจารณา live trading หลังตรวจสอบผลการทำงาน

8. **Database migrations ต้องรันตามลำดับ** ไฟล์ SQL 8 ไฟล์ใน `apps/backend/migrations/` ต้อง apply ตามลำดับ (0001 ถึง 0008) ก่อนที่ backend จะเริ่มทำงาน

9. **WebSocket reconnect อัตโนมัติ** ถ้า Binance WebSocket หลุด ระบบจะเชื่อมต่อใหม่ด้วย exponential backoff (สูงสุด 30 วินาที) พร้อมสร้างแจ้งเตือน `binance_disconnect`

10. **Model promotion ต้องทำเอง** การเทรนโมเดล AI ใหม่ไม่ได้ทำให้เป็น active โดยอัตโนมัติ ต้อง promote ผ่าน UI หรือ API โมเดล active เดิมจะยังคงอยู่จนกว่าจะถูกแทนที่
