# Softtrade — AI Trading Bot สำหรับ Binance (สเปกสำหรับ Claude Code)

Nov 19, 2026 · @Jakkrit Chaiwan

## 1. ภาพรวมโปรเจกต์

Softtrade คือ web app ที่รันบอทเทรดบน Binance โดยใช้ **หลายกลยุทธ์สลับตามสภาวะตลาด** มี **Risk Engine ที่มีอำนาจสูงสุด** และใช้ AI เป็น "นักวิเคราะห์ + ตัวกรองสัญญาณ" ไม่ใช่ผู้กดซื้อขายเอง เป้าหมายคือกำไรที่สม่ำเสมอหลังหักค่าธรรมเนียม และ drawdown ที่ควบคุมได้ ไม่ใช่กำไรสูงสุดในช่วงสั้น ๆ

**ขอบเขต v1**

- ตลาด: Binance Spot (เริ่มต้น) และ USDⓈ-M Futures (เปิดใช้ภายหลัง เลเวอเรจไม่เกิน 3x)
- เหรียญ: BTC, ETH, SOL, BNB, XRP และเพิ่มได้จาก watchlist (เฉพาะคู่ USDT ที่มีสภาพคล่องสูง)
- โหมดการทำงาน: Backtest → Paper (Testnet) → Live ทุกโหมดใช้โค้ดกลยุทธ์ชุดเดียวกัน
- ผู้ใช้: ผู้ใช้คนเดียวหรือทีมเล็ก (single-tenant) ออกแบบให้ขยายเป็น multi-user ได้

**หลักการออกแบบ 5 ข้อ (ให้ Claude Code ยึดตลอดโปรเจกต์)**

1. Risk first: ทุกคำสั่งต้องผ่าน Risk Engine ไม่มีทางลัด แม้แต่คำสั่งจาก AI หรือกดมือ
2. Same code everywhere: กลยุทธ์ต้องเป็น pure function ที่รับ candles + state แล้วคืน signal เพื่อให้ backtest กับ live ให้ผลตรงกัน
3. Exchange-side stops: stop-loss ต้องวางไว้บน Binance ทันทีหลัง fill ไม่พึ่งเซิร์ฟเวอร์เราอย่างเดียว
4. Fail safe: ข้อมูลค้าง, API error หรือ latency สูง → บอทหยุดเปิดออเดอร์ใหม่ (แต่ยังดูแลออเดอร์เดิม)
5. Explainable: ทุกการตัดสินใจบันทึกเหตุผล (indicator, คะแนน ML, ความเห็น AI, ผล risk check) ให้ย้อนดูได้

**วิธีใช้เอกสารนี้กับ Claude Code:** ใส่ไฟล์นี้ (export เป็น Markdown) ไว้ที่ `docs/SPEC.md` ใน repo แล้วสั่งงานทีละเฟสตามหัวข้อ 13 โดยอ้างอิงเลขหัวข้อ เช่น "ทำ Phase 2 ตาม SPEC.md หัวข้อ 3 และ 5"

## 2. กลยุทธ์การเทรด

ใช้แนว **Regime-switching ensemble**: ระบบจะจำแนกสภาวะตลาดก่อน แล้วเปิดเฉพาะกลยุทธ์ที่เหมาะกับสภาวะนั้น เหตุผลคือกลยุทธ์เดียวไม่มีทางชนะทุกสภาพตลาด trend following ขาดทุนในตลาด sideway ส่วน mean reversion ขาดทุนหนักตอนเทรนด์แรง

### 2.1 Regime Detector (คำนวณทุกแท่ง 4H)

| Regime | เงื่อนไข (ค่าเริ่มต้น ปรับได้จาก config) | กลยุทธ์ที่เปิด |
| --- | --- | --- |
| TREND\_UP | ADX(14) > 25, EMA50 > EMA200, EMA200 slope > 0 | S1 Trend, S3 Breakout (long) |
| TREND\_DOWN | ADX(14) > 25, EMA50 < EMA200 | Spot: ถือเงินสด · Futures: S1 short |
| RANGE | ADX(14) < 20, BB width ต่ำกว่า percentile 50 ของ 90 วัน | S2 Mean Reversion, S4 Grid |
| HIGH\_VOL | ATR(14)/price > percentile 90 หรือมีข่าวแรง (AI flag) | ปิดการเปิดออเดอร์ใหม่ หรือลด size 50% |

ใช้ regime ของ BTC เป็น "ตัวกรองตลาดรวม" ด้วย ถ้า BTC เป็น TREND\_DOWN ห้ามเปิด long เหรียญอื่น เพราะ altcoin มี correlation กับ BTC สูง

### 2.2 กลยุทธ์หลัก 4 ตัว

| กลยุทธ์ | Timeframe | เข้า | ออก / Stop |
| --- | --- | --- | --- |
| S1 Trend Pullback | เข้า 1H กรองทิศด้วย 4H | ราคาย่อกลับแตะ EMA20/EMA50 ใน regime TREND\_UP, RSI(14) กลับขึ้นเหนือ 50, แท่งปิดเหนือ EMA20 | SL = swing low − 0.5×ATR · TP1 2R (ปิด 50%) *(ปรับจาก 1.5R: ข้อ 3.5 บังคับ R:R ≥ 1.5 หลังค่าธรรมเนียม ซึ่ง 1.5R ทำไม่ได้ — ตัดสินใจเมื่อ 2026-11-20)* · ส่วนที่เหลือ trailing ด้วย Chandelier 3×ATR(22) |
| S2 Mean Reversion | 15m–1H | เฉพาะ RANGE: ราคาปิดต่ำกว่า BB(20,2) ล่าง + RSI(14) < 30 แล้วแท่งถัดไปปิดกลับเข้ากรอบ | TP = BB เส้นกลาง · SL = 1.5×ATR · ตัดทิ้งถ้าไม่ถึง TP ภายใน 12 แท่ง (time stop) |
| S3 Volatility Breakout | 4H | BB width อยู่ percentile < 20 (squeeze) แล้วราคาปิดทะลุ Donchian 20 พร้อม volume > 1.5× ค่าเฉลี่ย 20 แท่ง | SL = กลางกรอบ Donchian · trailing 2.5×ATR · ถ้ากลับเข้ากรอบภายใน 3 แท่ง = false breakout ปิดทันที |
| S4 Bounded Grid (Spot) | 1H | เฉพาะ RANGE: ตั้ง grid 10–20 ชั้นระหว่างแนวรับแนวต้าน ระยะห่างแต่ละชั้น ≥ 3× ค่าธรรมเนียมไปกลับ | หยุด grid และปิดสถานะทันทีถ้าราคาหลุดกรอบล่าง 1×ATR หรือ regime เปลี่ยน |

กลยุทธ์เสริม (ไม่ใช่บอทเก็งกำไร): **Smart DCA** ซื้อ BTC/ETH ตามรอบเวลา เพิ่มจำนวน 1.5–2 เท่าเมื่อ Fear & Greed < 25 และลดเมื่อ > 75 แยกพอร์ตออกจากบอทเทรด

### 2.3 การรวมสัญญาณ (Signal Scoring)

สัญญาณจากกลยุทธ์ไม่ได้ส่งออเดอร์ทันที แต่ถูกให้คะแนนรวม 0–100 ก่อน:

```latex
Score = 0.45 \cdot S_{tech} + 0.35 \cdot S_{ml} + 0.20 \cdot S_{ai}
```

- S\_tech: ความครบของเงื่อนไข + multi-timeframe alignment (เช่น 1H และ 4H ทิศเดียวกัน = คะแนนเต็ม)
- S\_ml: ความน่าจะเป็นที่ราคาถึง TP ก่อน SL จากโมเดล ML (หัวข้อ 4) × 100
- S\_ai: คะแนนความเห็นจาก AI Analyst (ข่าว, sentiment, funding, เหตุการณ์เศรษฐกิจ)
- Score ≥ 70 → เทรด size เต็ม · 60–69 → size 50% · < 60 → ไม่เข้า (บันทึกไว้เป็น skipped signal เพื่อวัดผลภายหลัง)
- น้ำหนักเป็นค่าเริ่มต้น ต้องปรับจากผล walk-forward ไม่ใช่จากความรู้สึก

### 2.4 ตัวกรองที่ใช้กับทุกกลยุทธ์

- Liquidity: volume 24h ≥ 50M USDT และ spread < 0.05%
- Funding (Futures): ไม่เปิด long เมื่อ funding > +0.05% ต่อรอบ (ตลาดร้อนเกิน) และไม่เปิด short เมื่อ < −0.05%
- Event blackout: หยุดเปิดออเดอร์ใหม่ 30 นาทีก่อนและหลังข่าวใหญ่ (CPI, FOMC, NFP) ตามปฏิทินเศรษฐกิจ
- Cooldown: หลังโดน stop ในเหรียญใด ห้ามเข้าเหรียญนั้นซ้ำ 4 ชั่วโมง
- คำนวณบนแท่งที่ปิดแล้วเท่านั้น (closed candle) เพื่อกัน repaint และ look-ahead bias

## 3. ระบบบริหารความเสี่ยง (Risk Engine)

Risk Engine คือส่วนที่สำคัญที่สุดของระบบ: เป็น service เดียวที่อนุมัติหรือปฏิเสธคำสั่ง และเป็นผู้คำนวณขนาดออเดอร์ กลยุทธ์และ AI บอกได้แค่ "ทิศทาง + จุด stop" ส่วนจำนวนเงินที่ใช้ Risk Engine เป็นคนกำหนด

### 3.1 Position Sizing (Fixed-fractional + volatility)

```latex
Qty = \frac{Equity \times Risk\% \times RegimeFactor \times ScoreFactor}{|Entry - StopLoss| + Fees + Slippage}
```

- Risk% ต่อเทรด: ค่าเริ่มต้น 0.5% ของ equity (สูงสุดที่อนุญาตใน config 1%)
- RegimeFactor: 1.0 ปกติ · 0.5 ใน HIGH\_VOL
- ScoreFactor: 1.0 เมื่อ Score ≥ 70 · 0.5 เมื่อ 60–69
- ปัดตาม filter ของ Binance ทุกครั้ง (LOT\_SIZE, PRICE\_FILTER/tickSize, MIN\_NOTIONAL) ถ้าปัดแล้วต่ำกว่า min notional ให้ข้ามเทรด
- Futures: ใช้ isolated margin, leverage สูงสุด 3x และตรวจว่าราคา liquidation อยู่ไกลกว่า stop-loss อย่างน้อย 2 เท่าของระยะ stop
- Kelly ใช้เพียงเป็นเพดาน (≤ ¼ Kelly) ไม่ใช้คำนวณ size ตรง ๆ

### 3.2 Exposure Limits

| เกณฑ์ | ค่าเริ่มต้น | เมื่อเกิน |
| --- | --- | --- |
| สถานะเปิดพร้อมกัน | 4 สถานะ | ปฏิเสธสัญญาณใหม่ |
| Exposure ต่อเหรียญ | 25% ของ equity | ลด size ให้พอดี |
| Exposure รวม (notional) | Spot 80% · Futures 150% | ปฏิเสธ |
| Open risk รวม (ผลรวมระยะถึง stop) | 2% ของ equity | ปฏิเสธ |
| Correlation bucket (เหรียญ corr > 0.8 นับเป็นกลุ่มเดียว) | open risk ต่อกลุ่ม 1.25% | ปฏิเสธ |
| เงินสดสำรอง | ≥ 20% เป็น USDT เสมอ | ปฏิเสธ |

### 3.3 Circuit Breakers และ Kill Switch

| ตัวกระตุ้น | เกณฑ์เริ่มต้น | การตอบสนอง |
| --- | --- | --- |
| Daily loss | −2% จาก equity ต้นวัน (00:00 UTC) | หยุดเปิดใหม่ถึงวันถัดไป |
| Weekly loss | −5% | หยุด 7 วัน + แจ้งเตือน |
| Max drawdown จาก peak | −12% | **Kill switch**: ยกเลิกออเดอร์ค้าง ปิดทุกสถานะ ต้อง reset ด้วยมือ + 2FA |
| แพ้ติดกัน | 4 ครั้ง | ลด Risk% ลงครึ่งจนกว่าจะชนะ 2 ครั้ง |
| Volatility spike | แท่ง 1m เคลื่อน > 3% หรือ ATR > 3× median 30 วัน | pause 60 นาที |
| Stale data | ไม่มี tick เกิน 10 วินาที | pause + reconnect |
| API error / rate limit | error ≥ 5 ครั้งใน 1 นาที หรือได้ HTTP 429 | backoff + pause; ได้ 418 = หยุดทันที |
| Slippage เฉลี่ย | > 0.15% ต่อเทรด (20 เทรดล่าสุด) | แจ้งเตือน + บังคับใช้ limit order |
| เหตุการณ์ฝั่ง exchange | AI/ข่าวพบ hack, หยุดถอน, depeg ของ stablecoin | pause + แจ้งเตือนให้คนตัดสินใจ (ไม่ปิดสถานะอัตโนมัติ) |

ปุ่ม Kill switch ต้องมีทุกหน้า (header) กดแล้วยืนยันหนึ่งครั้ง และมี CLI `softtrade kill` สำรองเผื่อเว็บล่ม

### 3.4 การจัดการออเดอร์เพื่อลดความเสี่ยง

1. เข้าด้วย LIMIT (maker ก่อน) ถ้าไม่ fill ใน N วินาทีให้ยกเลิก ไม่ไล่ราคา (ยกเว้น S3 breakout ใช้ market ได้)
2. ทันทีที่ได้ fill → วาง stop-loss บน exchange
   - Spot: OCO (STOP\_LOSS\_LIMIT + LIMIT\_MAKER เป็น TP)
   - USDⓈ-M Futures: วาง STOP\_MARKET / TAKE\_PROFIT\_MARKET แบบ reduce-only ผ่าน Algo Order endpoint (algoType=CONDITIONAL) ตาม [เอกสาร Binance](https://developers.binance.com/docs/derivatives/usds-margined-futures/trade/rest-api/Query-Algo-Order)
3. ถ้าวาง stop ไม่สำเร็จภายใน 3 วินาที → ปิดสถานะด้วย market ทันที (ห้ามมีสถานะที่ไม่มี stop)
4. TP1 ที่ 1.5R ปิด 50% แล้วย้าย stop ไป breakeven + ค่าธรรมเนียม
5. ทุกออเดอร์มี `newClientOrderId` แบบ idempotent (เช่น `st-{botId}-{signalId}-{leg}`) กันส่งซ้ำตอน retry
6. Reconciliation ทุก 60 วินาที: เทียบออเดอร์/สถานะใน DB กับ Binance ถ้าไม่ตรงกันให้เชื่อ Binance และบันทึก risk\_event

### 3.5 Pre-trade Checklist (ทุกข้อต้องผ่าน ไม่งั้น reject พร้อมเหตุผล)

1. Bot อยู่ในสถานะ RUNNING และไม่มี circuit breaker ทำงานอยู่
2. ข้อมูลราคาอายุ < 5 วินาที และ clock drift กับเซิร์ฟเวอร์ Binance < 500 ms
3. มี stop-loss และ R:R ≥ 1.5 (หลังค่าธรรมเนียม)
4. ผ่าน exposure limits ทุกข้อใน 3.2
5. ยอดเงินพอ และขนาดผ่าน filter ของ symbol
6. ไม่อยู่ใน event blackout และ cooldown

## 4. ระบบ AI วิเคราะห์

AI มี 2 ชั้นที่ทำงานต่างกัน: **ML Signal Model** (ตัวเลข เร็ว ทดสอบย้อนหลังได้) และ **LLM Analyst** (อ่านข่าว ตีความบริบท อธิบายเหตุผล) ทั้งคู่ทำได้แค่ "ให้คะแนน / ลด size / veto" ไม่มีสิทธิ์ส่งออเดอร์เอง และไม่มีสิทธิ์เพิ่ม size เกิน Risk Engine

### 4.1 ML Signal Model (ตัวกรองสัญญาณ)

- โมเดล: LightGBM classifier (เบา เร็ว อธิบายได้ด้วย SHAP) แยกโมเดลต่อกลยุทธ์
- โจทย์: "สัญญาณนี้จะถึง TP ก่อน SL ภายใน N แท่งไหม" ติด label ด้วย triple-barrier method (ไม่ทำนายราคาตรง ๆ เพราะ noise สูงเกินไป)
- Features: returns หลาย lag, RSI, ADX, ATR%, BB width percentile, ระยะห่างจาก EMA, volume z-score, taker buy ratio, order book imbalance (top 20 levels), funding rate, open interest change, BTC return (สำหรับ altcoin), ชั่วโมง/วันในสัปดาห์, regime
- Training: purged walk-forward CV (เว้นช่วง embargo กัน leakage) + Optuna หา hyperparameter, retrain ทุกสัปดาห์ด้วยข้อมูล rolling 12 เดือน
- Deploy: เก็บเวอร์ชันโมเดลใน MLflow (หรือโฟลเดอร์ models/ + metadata ใน DB) โมเดลใหม่ต้องชนะโมเดลเดิมบน out-of-sample ก่อน promote และมีปุ่ม rollback
- Monitoring: ติดตาม feature drift (PSI) และ calibration ถ้า precision 30 วันล่าสุดต่ำกว่า baseline ให้ตัด S\_ml ออกจากสูตรอัตโนมัติ

### 4.2 LLM Analyst (Claude API)

| งาน | โมเดล | ความถี่ | Output |
| --- | --- | --- | --- |
| จัดหมวดข่าวและ sentiment | claude-haiku-5-5 | ทุกข่าวใหม่ (batch ทุก 5 นาที) | JSON: เหรียญที่เกี่ยว, sentiment −1..1, ความรุนแรง 0..1, ประเภท (hack, listing, regulation, macro) |
| Market brief ต่อเหรียญ | claude-sonnet-5-5 | ทุก 4 ชั่วโมง + เมื่อมีข่าวแรง | JSON: bias (bull/neutral/bear), S\_ai 0..100, แนวรับ-ต้านที่ควรดู, ความเสี่ยง, สรุปภาษาไทย 3 บรรทัด |
| Trade review | claude-sonnet-5-5 | หลังปิดทุกเทรด + สรุปรายสัปดาห์ | บันทึก journal: ทำไมชนะ/แพ้, พบ pattern ที่ซ้ำ |
| AI Chat (ถามตอบ) | claude-sonnet-5-5 + tool use | ตามผู้ใช้ถาม | ตอบเรื่องพอร์ต/บอท โดยเรียก tool อ่านข้อมูลแบบ read-only |

**Input ที่ส่งให้ LLM:** สรุป indicator ที่คำนวณแล้ว (ไม่ส่ง candles ดิบทั้งก้อน), regime, ข่าว 24 ชม. ที่จัดหมวดแล้ว, funding/OI, Fear & Greed index, ปฏิทินเศรษฐกิจ

**กฎบังคับของ LLM layer**

- บังคับ output เป็น JSON ตาม schema (ใช้ tool use / structured output) แล้ว validate ด้วย Pydantic ถ้าผิด schema ให้ S\_ai = 50 (กลาง)
- Timeout 20 วินาที ถ้า LLM ล่มหรือช้า บอททำงานต่อด้วย S\_ai = 50 ไม่ค้างรอ
- ข่าวและเนื้อหาจากเว็บเป็น "ข้อมูล" ไม่ใช่คำสั่ง (กัน prompt injection) ครอบด้วย tag และสั่งใน system prompt ให้ไม่ทำตาม
- AI Chat ได้ tool แบบ read-only เท่านั้น (get\_positions, get\_bot\_stats, get\_analysis) การเปลี่ยน config ต้องให้ผู้ใช้กดยืนยันใน UI ทุกครั้ง
- ไม่ส่ง API key, ยอดเงินจริงแบบระบุตัวตน หรือข้อมูลส่วนตัวไปให้ LLM
- คุมค่าใช้จ่าย: cache ผล brief ตาม (symbol, ช่วงเวลา), ใช้ prompt caching กับ system prompt และตั้งงบรายเดือนพร้อมแจ้งเตือน
- บันทึก prompt, output, model version, token ในตาราง `ai_analyses` ทุกครั้ง เพื่อวัดว่า S\_ai ช่วยจริงไหม (ถ้าไม่ช่วย ให้ลดน้ำหนักเหลือ 0)

### 4.3 แหล่งข้อมูล

- ราคา/ออเดอร์บุ๊ก: Binance WebSocket Streams (kline, aggTrade, bookTicker, depth20) และ REST สำหรับ backfill
- Futures: funding rate, open interest, long/short ratio จาก Binance Futures API
- ข่าว: Binance announcements, RSS สำนักข่าวคริปโต, news aggregator API (เลือกตัวที่มี API อย่างเป็นทางการ)
- Fear & Greed index (ตรงกับการ์ด Market sentiment ในดีไซน์) และปฏิทินเศรษฐกิจ

## 5. สถาปัตยกรรมระบบ

ระบบแยกเป็น service เล็ก ๆ ที่คุยกันผ่าน Redis Streams เพื่อให้ส่วนที่ล่มไม่ลากส่วนอื่นล่มตาม เช่น AI ช้าหรือเว็บล่ม บอทก็ยังดูแล stop-loss ต่อได้

```
Binance Market Streams (kline · bookTicker · depth)
        │
        ▼
Market Data Service ──────────────► PostgreSQL + TimescaleDB · Redis Streams/PubSub
        │                                         ▲
        ▼                                         │ บันทึก / อ่าน
Strategy Engine (Regime + S1–S4 → Signal)         │
        │                                         │
News & Sentiment → AI Worker (LLM + ML) ──► Signal Scoring (S_tech + S_ml + S_ai → 0–100)
        │                                         │
        ▼                                         ▼
Risk Engine (คำนวณ size · อนุมัติ/ปฏิเสธ) ──────► API Gateway (FastAPI · REST + WS) ──► Web App (React)
        │
        ▼
Execution Service (ส่งคำสั่ง · วาง stop · reconcile)
        │  ▲ fills (user data stream)
        ▼  │
Binance Trade API (WebSocket API · REST)
```

เส้นทางเงินจริงคือคอลัมน์กลางจากบนลงล่าง AI Worker เป็นแค่ผู้ให้คะแนนทางซ้าย ส่วน Web App ทางขวารับ event ผ่าน API Gateway และสั่งงานได้เฉพาะผ่าน Risk Engine (รวมปุ่ม kill switch)

| Service | หน้าที่ | หากล่ม |
| --- | --- | --- |
| market-data | รับ stream จาก Binance, ปิดแท่ง, เก็บ DB, publish `candles.closed` | บอท pause ตามกฎ stale data |
| strategy | รับ `candles.closed` → regime + กลยุทธ์ → scoring → publish `signals.new` | ไม่มีสัญญาณใหม่ สถานะเดิมมี stop บน exchange แล้ว |
| risk-exec | Risk Engine + Execution + reconciler (process เดียว เพื่อไม่มี race) | supervisor restart ทันที แล้ว reconcile ก่อนทำงานต่อ |
| ai-worker | ข่าว, LLM brief, ML inference, เขียน S\_ai/S\_ml ลง Redis cache | scoring ใช้ค่ากลาง 50 |
| api | REST + WebSocket ให้ frontend, auth | เทรดต่อได้ ดูผ่าน Telegram/CLI |
| scheduler | retrain ML, daily reset, snapshot equity, backup | งานรอบถัดไปทำชดเชย |

## 6. Tech Stack

แนะนำ **Python (FastAPI) เป็น backend หลัก + React (Vite) เป็น frontend** เพราะงาน quant/ML (pandas, numpy, LightGBM, Optuna) และ Claude SDK อยู่บน Python ทั้งหมด ใช้ภาษาเดียวจึงได้โค้ดกลยุทธ์ชุดเดียวทั้ง backtest และ live ส่วนความเร็วพอสำหรับกลยุทธ์ timeframe 15m–4H (ไม่ใช่ HFT)

### 6.1 Backend

| ส่วน | เลือกใช้ | เหตุผล |
| --- | --- | --- |
| ภาษา / runtime | Python 3.12+ (asyncio, uvloop), จัดการ dependency ด้วย uv | ecosystem quant/ML ครบที่สุด |
| API | FastAPI + Pydantic v2 + WebSocket | async, สร้าง OpenAPI ให้ frontend generate type ได้ |
| Binance | Binance official Python SDK แบบ modular (spot, derivatives) ห่อด้วย `ExchangeAdapter` interface ของเรา · ccxt เป็นทางเลือกถ้าจะรองรับหลาย exchange | adapter เดียวสลับได้ 3 แบบ: Live, Testnet, Simulated (backtest) |
| Indicators | pandas + numpy + TA-Lib (หรือ pandas-ta) | เร็วและมาตรฐาน |
| ML | LightGBM, scikit-learn, Optuna, SHAP, MLflow | เบา อธิบายได้ ไม่ต้องใช้ GPU |
| LLM | Anthropic Python SDK (Claude) | tool use + structured output |
| Backtest | event-driven backtester ของเราเอง (ใช้ strategy code เดียวกับ live) + vectorbt สำหรับสแกนพารามิเตอร์เร็ว ๆ | ผล backtest ตรงกับ live มากที่สุด |
| Database | PostgreSQL 16+ + TimescaleDB (hypertable สำหรับ candles, equity) | SQL เดียวจบ ทั้งข้อมูลธุรกรรมและ time-series |
| ORM / migration | SQLAlchemy 2 (async) + Alembic | มาตรฐาน |
| Cache / message bus | Redis 7 (Streams ส่ง event ระหว่าง service, Pub/Sub ส่งขึ้น UI, lock) | เร็ว ง่าย ไม่ต้องใช้ Kafka |
| Scheduler / jobs | APScheduler (งานตามเวลา) + arq (job queue บน Redis สำหรับ backtest/AI) | ไม่บล็อก event loop ของบอท |
| Test | pytest, pytest-asyncio, hypothesis (property test กับ Risk Engine) | Risk Engine ต้อง coverage ≥ 95% |

### 6.2 Frontend

| ส่วน | เลือกใช้ | เหตุผล |
| --- | --- | --- |
| Framework | React + TypeScript + Vite (SPA) | dashboard หลัง login ไม่ต้องการ SSR, build เร็ว |
| Styling | Tailwind CSS v4 + CSS variables ตาม design tokens (หัวข้อ 9) | คุมเงา neumorphic ได้แม่นยำ |
| Components | Radix UI primitives (ผ่าน shadcn/ui แล้ว restyle) | accessible, ไม่ผูกสไตล์ |
| กราฟราคา | TradingView Lightweight Charts | เร็ว เบา ฟรี รองรับ candlestick/area/marker จุดเข้าออก |
| กราฟอื่น (equity, allocation) | Recharts หรือ visx | ปรับสไตล์ได้เต็มที่ |
| Server state | TanStack Query | cache + refetch อัตโนมัติ |
| Realtime state | Zustand store รับจาก WebSocket เดียว (multiplex หลาย channel) | ลด re-render ด้วย selector |
| Router / form | TanStack Router (หรือ React Router) + React Hook Form + Zod | type-safe |
| API types | openapi-typescript generate จาก FastAPI | type ตรงกับ backend เสมอ |
| Font / icon | Poppins (หัวข้อ/ตัวเลข) + IBM Plex Sans Thai (ภาษาไทย) · Lucide icons | ตรงกับดีไซน์ |

### 6.3 Infrastructure

- Docker Compose (เริ่มต้น) แยก container: api, market-data, strategy, risk-exec, ai-worker, scheduler, postgres, redis, caddy
- เซิร์ฟเวอร์: VPS 2 vCPU / 4 GB พอสำหรับ v1 เลือก region ใกล้ Binance (นิยมใช้ AWS Tokyo ap-northeast-1) และต้องมี static IP สำหรับ IP whitelist ของ API key
- Reverse proxy: Caddy (HTTPS อัตโนมัติ)
- Observability: Prometheus + Grafana (latency, error rate, PnL), Sentry (error), log แบบ JSON ด้วย structlog
- แจ้งเตือน: Telegram Bot API (หลัก) และ LINE Messaging API (ทางเลือก)
- CI/CD: GitHub Actions → lint (ruff, mypy, eslint) → test → build image → deploy
- Backup: pg\_dump ทุกวันขึ้น object storage แบบเข้ารหัส

**ตัดสินใจ: ใช้ Python ล้วนสำหรับ v1** เพราะกลยุทธ์ 15m–4H ไม่ได้แพ้ชนะกันที่ระดับมิลลิวินาที และ latency ส่วนใหญ่มาจากเครือข่ายไป Binance ไม่ใช่ภาษา ภาษาเดียวทำให้ backtest กับ live ใช้โค้ดชุดเดียวกันได้จริง ไม่ต้องดูแลสอง codebase และ contract ระหว่างภาษา ค่อยพิจารณาย้าย API gateway หรือ execution ไป Go เมื่อเจอเงื่อนไขใดเงื่อนไขหนึ่ง: ผู้ใช้หลายร้อยคนหรือบอทหลายร้อยตัวพร้อมกัน, ทำ market making หรือกลยุทธ์ที่ต้องตอบสนองต่ำกว่า 10 ms, หรือวัดแล้วพบว่า event loop ของ Python เป็นคอขวด เนื่องจาก service คุยกันผ่าน Redis Streams และ `ExchangeAdapter` อยู่แล้ว การย้ายทีละ service ภายหลังจึงไม่ต้องรื้อระบบ ส่วน NautilusTrader (แกน Rust มี adapter Binance) เก็บไว้เป็นตัวเลือกสำรองถ้าอยากได้เฟรมเวิร์กสำเร็จรูป

## 7. Data Model (PostgreSQL + TimescaleDB)

จำนวนเงินทุกช่องใช้ `NUMERIC(28,10)` (ห้ามใช้ float) เวลาทุกช่องเป็น `TIMESTAMPTZ` เก็บแบบ UTC และทุกตารางมี `created_at` / `updated_at`

| ตาราง | คอลัมน์หลัก | หมายเหตุ |
| --- | --- | --- |
| users | id, email, password\_hash (argon2id), totp\_secret\_enc, role |  |
| exchange\_accounts | id, user\_id, exchange, label, api\_key\_enc, api\_secret\_enc, key\_type (HMAC/Ed25519), is\_testnet, permissions\_checked\_at | key เข้ารหัสแบบ envelope (หัวข้อ 12) |
| bots | id, account\_id, name, market (SPOT/USDM), symbols\[\], status (DRAFT/PAPER/RUNNING/PAUSED/KILLED), mode (backtest/paper/live), risk\_profile\_id |  |
| strategy\_configs | id, bot\_id, strategy (S1..S4), params JSONB, version, is\_active | สร้างเวอร์ชันใหม่ทุกครั้งที่แก้ ห้ามแก้ทับ |
| risk\_profiles | id, risk\_per\_trade, max\_positions, daily\_loss, weekly\_loss, max\_dd, max\_leverage, ... | ค่าเริ่มต้นตามหัวข้อ 3 |
| candles (hypertable) | symbol, interval, open\_time, o, h, l, c, v, quote\_v, trades, taker\_buy\_v | PK (symbol, interval, open\_time) + บีบอัดข้อมูลเก่ากว่า 7 วัน |
| market\_metrics (hypertable) | symbol, ts, funding\_rate, open\_interest, ls\_ratio, fear\_greed |  |
| signals | id, bot\_id, symbol, strategy, side, entry, stop, tp1, s\_tech, s\_ml, s\_ai, score, decision (TAKEN/SKIPPED/REJECTED), reject\_reason | เก็บทุกสัญญาณ รวมตัวที่ข้าม |
| ai\_analyses | id, symbol, kind (news/brief/review/chat), model, prompt\_hash, input JSONB, output JSONB, tokens\_in/out, cost\_usd, latency\_ms |  |
| news\_items | id, source, url, title, published\_at, symbols\[\], sentiment, severity, category |  |
| orders | id, bot\_id, signal\_id, client\_order\_id (unique), exchange\_order\_id, symbol, side, type, price, qty, status, leg (ENTRY/SL/TP/EXIT), raw JSONB |  |
| fills | id, order\_id, trade\_id, price, qty, fee, fee\_asset, is\_maker, ts |  |
| positions | id, bot\_id, symbol, side, qty, avg\_entry, stop, unrealized\_pnl, status (OPEN/CLOSED), opened\_at, closed\_at |  |
| trades | id, position\_id, pnl\_usdt, pnl\_r, fees, slippage, holding\_minutes, exit\_reason | 1 แถวต่อ 1 รอบเทรด ใช้คำนวณสถิติ |
| equity\_snapshots (hypertable) | account\_id, ts, equity, cash, exposure, drawdown | บันทึกทุก 1 นาที |
| risk\_events | id, bot\_id, type, severity, payload JSONB, resolved\_by, resolved\_at |  |
| backtests | id, strategy\_config\_snapshot, range, fees\_model, metrics JSONB, equity\_curve\_ref, status |  |
| audit\_log | id, user\_id, action, target, before JSONB, after JSONB, ip, ts | เขียนเพิ่มได้อย่างเดียว (append-only) |

## 8. API และ WebSocket Contract

REST อยู่ใต้ `/api/v1` ใช้ JWT (access token 15 นาที + refresh token ใน httpOnly cookie) คำสั่งที่กระทบเงินจริง (เปิดบอทโหมด live, แก้ risk profile, reset kill switch, เพิ่ม API key) ต้องส่ง TOTP ใน header `X-TOTP` ด้วย

### 8.1 REST Endpoints

| Method | Path | หน้าที่ |
| --- | --- | --- |
| POST | /auth/login, /auth/refresh, /auth/logout, /auth/totp/setup | เข้าระบบ + 2FA |
| GET | /dashboard/summary | ยอดพอร์ต, PnL วันนี้, available, in orders, allocation |
| GET | /markets/{symbol}/candles?interval=&limit= | กราฟราคา |
| GET | /markets/{symbol}/stats | 24h high/low/volume, funding |
| GET / PUT | /watchlist | รายการเหรียญที่ติดตาม |
| GET / POST | /accounts | จัดการ API key (ตอบกลับเฉพาะ 4 ตัวท้าย) |
| POST | /accounts/{id}/verify | ตรวจสิทธิ์ key: ต้อง trade ได้ แต่ถอนไม่ได้ |
| GET / POST / PATCH | /bots, /bots/{id} | CRUD บอท |
| POST | /bots/{id}/start, /pause, /stop | ควบคุมบอท |
| GET | /bots/{id}/performance?range= | equity curve, win rate, PF, max DD, Sharpe |
| GET | /signals?bot\_id=&decision= | สัญญาณพร้อมเหตุผล |
| GET | /orders?status=all\|open\|filled, /positions, /trades | ประวัติ |
| POST | /orders (manual) · DELETE /orders/{id} | ส่งออเดอร์เอง (ผ่าน Risk Engine เหมือนกัน) |
| GET / PUT | /risk/profile, GET /risk/status, GET /risk/events | ดูและตั้งค่าความเสี่ยง |
| POST | /risk/kill · /risk/kill/reset | kill switch |
| GET | /ai/briefs?symbol= · POST /ai/briefs/refresh | บทวิเคราะห์ AI |
| POST | /ai/chat (stream แบบ SSE) | AI ถามตอบ |
| GET | /sentiment | Fear & Greed + sentiment รวม |
| POST | /backtests · GET /backtests/{id} | สั่ง backtest (ทำใน job queue) |

### 8.2 WebSocket `/ws`

เชื่อมต่อเดียวต่อแท็บ ส่ง `{"op":"subscribe","channels":["ticker:BTCUSDT","orders"]}` ทุก message มีรูปแบบ `{"ch": string, "ts": number, "data": object}`

| Channel | ข้อมูล | ความถี่ |
| --- | --- | --- |
| ticker:{symbol} | last, change24h, high, low, volume | throttle 1 ครั้ง/วินาที |
| kline:{symbol}:{interval} | แท่งล่าสุด (กำลังก่อตัว) | throttle 1 ครั้ง/วินาที |
| portfolio | equity, pnl\_today, available, in\_orders | ทุก 5 วินาที |
| orders · positions | เมื่อสถานะเปลี่ยน | event |
| bots | status, สัญญาณล่าสุด | event |
| risk | circuit breaker, kill switch | event (แสดง toast + เสียง) |
| ai | brief ใหม่, ข่าว severity สูง | event |

### 8.3 การเชื่อม Binance ด้านใน

- Market data: ใช้ combined streams (หลาย stream ใน connection เดียว) ต่ออัตโนมัติก่อนครบ 24 ชม. และ backfill แท่งที่หายด้วย REST หลัง reconnect
- Spot user data (ออเดอร์/ยอดเงิน): ใช้ `userDataStream.subscribe.signature` บน WebSocket API เพราะการรับ user data ด้วย listenKey บน stream.binance.com ถูก deprecate แล้ว ([Binance](https://www.binance.com/en/support/announcement/e68ef81d456a4cba8fd63d0267cc2736))
- USDⓈ-M Futures user data: ยังใช้ listenKey (`POST /fapi/v1/listenKey` + keepalive) ([Binance](https://developers.binance.com/en/docs/products/caas/user-data-streams))
- ส่งออเดอร์: WebSocket API (latency ต่ำกว่า REST) และ fallback เป็น REST
- อ่าน `rateLimits` / header used-weight ทุก response และชะลอเมื่อใช้เกิน 80% ของ limit
- Sync เวลากับ `GET /api/v3/time` ทุก 10 นาที ใช้ `recvWindow` 5000 ms
- แนะนำใช้ Ed25519 API key (จำเป็นสำหรับ session logon บน WebSocket API)
- Testnet: Spot ใช้ testnet.binance.vision · Futures ใช้ `https://demo-fapi.binance.com` และ `wss://demo-fstream.binance.com` ([Binance](https://developers.binance.com/docs/derivatives/usds-margined-futures))

## 9. Design System (Soft Neumorphic ตามไฟล์แนบ)

ดีไซน์ใช้พื้นหลังและการ์ดสีเดียวกัน (เทาอมฟ้า) แยกชั้นด้วยเงาสองทิศ มีสีเน้น (accent) เพียงสีเดียวคือเหลืองทอง นี่คือเหตุผลที่ UI ดูไม่รก ค่าสีด้านล่างเป็นชุดสุดท้าย ปรับจากไฟล์แบบให้สว่างตาและผ่าน WCAG AA (ตัวอักษรบนพื้นหลัง contrast ≥ 4.5:1) ให้ Claude Code ใช้ตามนี้ได้เลย

### 9.1 Color Tokens

| Token | Light | Dark | ใช้กับ | Contrast บนพื้น (Light / Dark) |
| --- | --- | --- | --- | --- |
| --bg / --surface | #E6E9EF | #1D2027 | พื้นหลังและการ์ด (สีเดียวกัน) | — |
| --shadow-light | #FFFFFF | #2A2E37 | เงาด้านบนซ้าย | — |
| --shadow-dark | #C5CBD6 | #131519 | เงาด้านล่างขวา | — |
| --text-primary | #1C1F26 | #E9EBF0 | ตัวเลขและหัวข้อ | 13.6 / 13.7 |
| --text-secondary | #5E6574 | #9BA1AE | label และคำอธิบาย | 4.8 / 6.3 |
| --accent | #E9B026 | #F2BE3C | ปุ่มหลัก, เส้นกราฟ, badge Open, แท่ง allocation | ใช้เป็นพื้นเท่านั้น |
| --on-accent | #1C1F26 | #1D2027 | ตัวอักษรบนปุ่ม/badge เหลือง | 8.4 / 9.5 (บน accent) |
| --accent-fill | --accent @ 14% | --accent @ 18% | พื้นใต้กราฟ area, hover แถว | — |
| --up | #0F7240 | #3DD68C | ราคาขึ้น, Buy, PnL บวก | 4.9 / 8.7 |
| --down | #B8332A | #FF6B61 | ราคาลง, Sell, PnL ลบ | 4.9 / 5.8 |
| --ink | #1C1F26 | #F4F5F7 | tooltip, avatar, ป้ายราคาบนกราฟ | — |
| --focus | #2F6FEB | #6EA0FF | focus ring 2px ของทุก control | แยกจาก accent เพื่อไม่สับสนกับปุ่มหลัก |

**กฎสี:** เหลืองใช้เป็นพื้นหรือเส้นกราฟเท่านั้น ห้ามใช้เป็นสีตัวอักษรบนพื้นเทา (contrast แค่ 1.6:1) และมี action สีเหลืองได้ไม่เกิน 1 จุดต่อการ์ด · เขียว/แดงใช้กับตัวเลขและตัวอักษรเท่านั้น ห้ามทาพื้นการ์ด และใส่เครื่องหมาย + / − หน้าตัวเลขเสมอ เพื่อให้คนตาบอดสีอ่านได้ · สถานะ KILLED / error ใช้ --down เป็นตัวอักษรบน badge นูนปกติ · Dark mode ใช้เงาเบาลง (opacity เงาสว่างต่ำ) เพราะ neumorphism บนพื้นมืดดูเปื้อนง่าย

### 9.2 เงาและระดับชั้น (Elevation)

```css
:root {
  --raised-lg: 10px 10px 24px var(--shadow-dark), -10px -10px 24px var(--shadow-light);  /* การ์ดหลัก */
  --raised-sm: 4px 4px 10px var(--shadow-dark), -4px -4px 10px var(--shadow-light);    /* ปุ่ม, chip, แถว watchlist */
  --inset:     inset 4px 4px 8px var(--shadow-dark), inset -4px -4px 8px var(--shadow-light); /* input, พื้นกราฟ, แท่ง allocation */
  --pressed:   inset 2px 2px 5px var(--shadow-dark), inset -2px -2px 5px var(--shadow-light); /* ปุ่มที่ถูกเลือก (1D, 50%, All) */
}
```

- 3 ระดับเท่านั้น: raised (นูนขึ้นกดได้), inset (พื้นที่ใส่ข้อมูล/แสดงข้อมูล), pressed (สถานะถูกเลือก) ห้ามซ้อนเงาเกิน 2 ชั้น
- Neumorphism มี contrast ต่ำโดยธรรมชาติ จึงต้องใช้ตัวอักษรเข้ม (--text-primary) กับข้อมูลสำคัญ, มี focus ring 2px สี accent ทุก control และไม่พึ่งเงาอย่างเดียวบอกว่ากดได้ (ผ่าน WCAG AA)
- เคารพ `prefers-reduced-motion` และ transition เงา 150 ms

### 9.3 Typography, Radius, Spacing

| ส่วน | ค่า |
| --- | --- |
| Font | Poppins (Latin/ตัวเลข) + IBM Plex Sans Thai (ไทย) · ตัวเลขทุกจุดใช้ `font-variant-numeric: tabular-nums` |
| Display (ยอดพอร์ต) | 40/48 Bold ส่วนทศนิยม 24 Medium สี secondary (เช่น $128,460.72) |
| H2 (ราคาหลัก) | 22/28 SemiBold |
| Card title | 15/20 SemiBold + subtitle 11/16 สี secondary |
| Body / table | 13/20 Regular · หัวตาราง 11/16 สี secondary |
| Radius | card 24 · inner panel 16 · input/ปุ่ม 14 · chip/badge/segmented 999 |
| Spacing | grid 8 pt · padding การ์ด 24 · gap ระหว่างการ์ด 24 · ความกว้างสูงสุดเนื้อหา 1440 px |

### 9.4 Component Inventory (สร้างเป็น component กลางใน `src/ui/`)

- `Card` (title, subtitle, action slot) · `InsetPanel` · `StatTile` (label + value เช่น 24h high)
- `Segmented` (1H/4H/1D/1W/1M, Buy/Sell, All/Open/Filled) · `PercentChips` (25/50/75/100%)
- `IconButton` (กลม raised + label ด้านล่าง: Deposit/Withdraw/Convert/More) · `PrimaryButton` (เหลืองเต็ม)
- `NumberInput` (inset + หน่วยด้านขวา เช่น USDT/BTC, ปัดตาม tickSize/stepSize อัตโนมัติ)
- `AssetRow` (ไอคอนกลมตัวอักษร + ชื่อ + sparkline + ราคา + %change)
- `PriceChart` (Lightweight Charts area เส้นเหลือง + ป้ายราคาสี ink, สลับ candlestick ได้, marker จุดเข้าออกของบอท)
- `Gauge` (Fear & Greed แบบขีด) · `AllocationBars` (แท่งแนวตั้ง inset + เติมเหลือง)
- `DataTable` (แถวแยกด้วยเส้นบาง ไม่มี zebra) · `StatusBadge` (Filled = นูนเทา, Open = เหลือง, Cancelled = นูนเทาตัวอักษรจาง)
- `MarketStatusPill` (จุดสี + "Market open") · `BotStatusPill` (RUNNING / PAUSED / KILLED)
- `Toast`, `ConfirmDialog` (มีช่อง TOTP สำหรับคำสั่งเสี่ยง), `Skeleton` ทรงเดียวกับการ์ดจริง

## 10. หน้าจอ UI

แอปมี 7 หน้า แต่ละหน้ามีไม่เกิน 6–7 การ์ด และใช้ grid 12 คอลัมน์เหมือนไฟล์แบบ การนำทางใช้ **แถบไอคอนแนวตั้งซ้ายกว้าง 72 px** (tooltip ชื่อหน้า) แทน sidebar เต็ม เพื่อคงความโล่งของดีไซน์ ส่วน header คงตามไฟล์แบบ (โลโก้, วันที่, ช่องค้นหา, Market open, แจ้งเตือน, theme, โปรไฟล์) และเพิ่ม 2 อย่าง: `BotStatusPill` รวม (เช่น "3 bots running") และปุ่ม Kill switch รูปโล่

| # | หน้า | การ์ดหลัก | หมายเหตุ |
| --- | --- | --- | --- |
| 1 | Dashboard | Portfolio balance · Price chart · Watchlist · Bots & AI insight · Market sentiment · Allocation · Recent orders | ตามไฟล์แบบ แต่การ์ดกลางเปลี่ยนจาก Place order เป็น Bots & AI insight (ดูด้านล่าง) |
| 2 | Trade | Price chart ใหญ่ (candlestick + marker บอท) · Place order · Order book ย่อ · Open orders | การ์ด Place order ย้ายมาอยู่ที่นี่ แสดง "ความเสี่ยงของออเดอร์นี้ = x% ของพอร์ต" ก่อนกด |
| 3 | Bots | รายการบอทเป็นการ์ด (ชื่อ, กลยุทธ์, สถานะ, PnL 7 วัน, sparkline equity) · ปุ่ม New bot | สร้างบอทเป็น wizard 4 ขั้น: ตลาด & เหรียญ → กลยุทธ์ (preset) → Risk profile → Backtest สรุปแล้วค่อยเริ่ม Paper |
| 4 | Bot detail | KPI (Net PnL, Win rate, Profit factor, Max DD, Sharpe) · Equity curve + drawdown · Signals (รวมที่ข้ามพร้อมเหตุผล) · Trades · Config · Logs | คลิกสัญญาณแล้วเห็นคะแนน S\_tech/S\_ml/S\_ai และผล risk check ทุกข้อ |
| 5 | AI Analyst | เลือกเหรียญ → Market brief (bias, แนวรับ-ต้าน, ความเสี่ยง) · News feed พร้อม sentiment · AI Chat ด้านขวา | ทุกคำตอบ AI มีเวลาที่วิเคราะห์และ disclaimer สั้น ๆ |
| 6 | Backtest Lab | ฟอร์มเลือกกลยุทธ์/ช่วงเวลา/ค่าธรรมเนียม · ผล: KPI, equity vs buy & hold, ตาราง walk-forward แต่ละ fold, heatmap พารามิเตอร์ | แสดงคำเตือน overfitting ถ้า in-sample ดีกว่า out-of-sample มาก |
| 7 | Risk & Settings | Risk profile (slider + ค่าตัวเลข), สถานะ circuit breaker, risk events · API keys, แจ้งเตือน (Telegram/LINE), 2FA, theme | แก้ค่าเสี่ยงต้องยืนยัน TOTP |

### 10.1 Dashboard (ปรับจากไฟล์แบบ)

- แถว 1: Portfolio balance (3 col) · Price chart (9 col) คงเดิม เพิ่ม marker จุดเข้า/ออกของบอทบนกราฟ
- แถว 2: Watchlist (4 col) · **Bots & AI insight** (4 col) · Market sentiment + Allocation ซ้อนกัน (4 col)
  - Bots & AI insight: บนสุดคือสรุปบอท (จำนวนที่ทำงาน, PnL วันนี้, open risk เทียบเพดาน 2%) ตามด้วย AI brief ของเหรียญที่เลือก 3 บรรทัด + bias chip และปุ่มเหลือง "Open bot"
- แถว 3: Recent orders เพิ่มคอลัมน์ Source (ชื่อบอท หรือ Manual) และ PnL ของออเดอร์ปิดสถานะ

### 10.2 กฎความไม่รก

- 1 การ์ด = 1 คำถาม ("พอร์ตเป็นอย่างไร", "บอททำอะไรอยู่") ตัวเลขเด่นได้ไม่เกิน 1 ตัวต่อการ์ด
- รายละเอียดรองซ่อนไว้ใน drawer ด้านขวา (คลิกแถวออเดอร์/สัญญาณ) แทนการเพิ่มการ์ด
- ตัวเลขทศนิยมตาม tickSize ของเหรียญ, ย่อเป็น K/M เมื่อเกิน 6 หลัก, กระพริบสีเขียว/แดงเบา ๆ 300 ms เมื่อราคาเปลี่ยน
- Empty / loading / error state ทุกการ์ด (เช่น "ยังไม่มีบอท — สร้างบอทแรกในโหมด Paper")
- โหมด Paper แสดงแถบสีเหลืองบาง ๆ บนสุด "PAPER TRADING" ตลอด กันสับสนกับเงินจริง
- Responsive: ≥ 1280 ตามแบบ · 768–1279 เหลือ 2 คอลัมน์ · < 768 เรียงการ์ดเดียว แท็บบาร์ล่าง และตารางกลายเป็น list

## 11. Backtest, Paper Trading และเกณฑ์ก่อนใช้เงินจริง

กลยุทธ์จะขึ้นเงินจริงได้ต้องผ่าน 3 ด่านตามลำดับและระบบต้องบังคับขั้นตอนนี้ในโค้ด (บอทที่ไม่มี backtest ผ่านเกณฑ์จะกด Go live ไม่ได้)

### 11.1 มาตรฐาน Backtest

- ข้อมูล ≥ 3 ปี ครอบคลุมทั้งตลาดขาขึ้น ขาลง และ sideway (ดาวน์โหลดจาก Binance public data / REST klines)
- Event-driven ทีละแท่ง ใช้ strategy class เดียวกับ live ผ่าน `SimulatedExchangeAdapter`
- ค่าธรรมเนียมตั้งค่าได้ใน config ตั้งต้นแบบอนุรักษ์นิยมคือ taker ทุกออเดอร์ (ตรวจอัตราปัจจุบันจากหน้า fee ของ Binance ตาม VIP level จริง) + slippage 0.05% ต่อด้าน + funding จริงของ Futures
- Stop และ TP ที่อยู่ในแท่งเดียวกัน: สมมติว่าโดน stop ก่อน (worst case) หรือใช้ข้อมูล 1m ตัดสิน
- Walk-forward: optimize บน 12 เดือน → ทดสอบ 3 เดือนถัดไป → เลื่อนไปเรื่อย ๆ รายงานเฉพาะผล out-of-sample รวม
- Robustness: Monte Carlo สลับลำดับเทรด 1,000 รอบ หา max DD ที่ percentile 95 และทดสอบว่าพารามิเตอร์ใกล้เคียง (±20%) ยังกำไร (ไม่ใช่จุดสูงสุดเพียงจุดเดียว)

### 11.2 เกณฑ์ผ่านแต่ละด่าน

| ด่าน | ระยะเวลา / เงิน | เกณฑ์ผ่าน (หลังค่าธรรมเนียม) |
| --- | --- | --- |
| 1. Backtest (out-of-sample) | ≥ 3 ปีข้อมูล | ≥ 100 เทรด, Profit factor ≥ 1.3, Sharpe ≥ 1.0, Max DD ≤ 20%, expectancy > 0.15R, ไม่มีปีไหนขาดทุนเกิน 10% |
| 2. Paper (Testnet / Demo) | ≥ 4 สัปดาห์ | ผลเบี่ยงจาก backtest ช่วงเดียวกันไม่เกิน 30%, ไม่มี order error ที่ไม่ได้จัดการ, reconciliation ตรง 100% |
| 3. Live ทุนเล็ก | 4–8 สัปดาห์ ด้วย 5–10% ของทุนที่ตั้งใจ | slippage เฉลี่ยอยู่ในสมมติฐาน, DD ไม่เกิน Monte Carlo p95 → ค่อยเพิ่มทุนทีละ 25% |

ตัวเลขเกณฑ์เป็นค่าเริ่มต้นที่เข้มพอสมควรสำหรับกลยุทธ์ timeframe กลาง ปรับได้ใน config แต่ไม่ควรลดลงเพียงเพื่อให้กลยุทธ์ผ่าน หลัง live แล้วถ้า profit factor 60 เทรดล่าสุดต่ำกว่า 1.0 ให้ระบบเสนอให้ย้อนกลับไป Paper อัตโนมัติ

## 12. Security และการจัดการ API Key

กฎที่สำคัญที่สุด: **API key ของบอทต้องถอนเงินไม่ได้เด็ดขาด** ถ้า key หลุด ความเสียหายสูงสุดจะจำกัดอยู่ที่การเทรดที่ผิดปกติ ไม่ใช่การถูกถอนเงินออก

**การตั้งค่าฝั่ง Binance**

- เปิดเฉพาะ Reading + Spot & Margin Trading (+ Futures ถ้าใช้) · ปิด Withdrawals และ Universal Transfer
- ผูก IP whitelist กับ static IP ของเซิร์ฟเวอร์เท่านั้น
- แนะนำใช้ sub-account แยกสำหรับบอท โอนเฉพาะทุนที่ให้บอทใช้ และใช้ Ed25519 key
- ปุ่ม `/accounts/{id}/verify` ต้องเรียก API ตรวจสิทธิ์ key จริง ถ้าพบว่า key ถอนเงินได้หรือไม่มี IP restriction ให้ปฏิเสธไม่บันทึก

**ฝั่งแอป**

- เข้ารหัส key แบบ envelope encryption: data key (AES-256-GCM) ต่อ record ห่อด้วย master key จาก KMS (AWS KMS / GCP KMS) หรืออย่างน้อย libsodium + master key ใน env ที่ไม่อยู่ใน repo
- ถอดรหัส key เฉพาะใน service risk-exec เท่านั้น API service และ AI worker ไม่มีสิทธิ์ถอดรหัส
- ห้าม log key/secret/signature เด็ดขาด (ใส่ log redaction filter) และห้ามส่งให้ LLM
- Login: argon2id + TOTP บังคับ, rate limit login 5 ครั้ง/15 นาที, session timeout 12 ชม.
- Web: HTTPS เท่านั้น, CSP เข้ม, CORS เฉพาะ origin ของเรา, cookie `Secure; HttpOnly; SameSite=Strict`, ป้องกัน CSRF
- ทุกการเปลี่ยน config / start-stop บอท / kill บันทึก audit\_log
- Dependency scan (pip-audit, npm audit, Dependabot) และ secret scan (gitleaks) ใน CI
- แจ้งเตือน Telegram ทันทีเมื่อ login จาก IP ใหม่ หรือมีการเพิ่ม/แก้ API key

## 13. แผนพัฒนาและ Prompt สำหรับ Claude Code

แบ่งงานเป็น 8 เฟส สั่งทีละเฟส ตรวจผล แล้ว commit ก่อนไปเฟสถัดไป เฟส 0–3 คือแกนที่ทำเงิน (backend) ควรทำให้เสถียรก่อนแต่ง UI

```
Phase 0 Scaffold → Phase 1 Market data + DB → Phase 2 Strategies + Backtester → Phase 3 Risk + Execution (testnet)
   → [Gate A: Paper ผ่านเกณฑ์หัวข้อ 11.2]
Phase 4 Design system + Dashboard → Phase 5 App pages → Phase 6 AI layer → Phase 7 Hardening
   → [Gate B: Live ทุนเล็ก 5–10%]
```

Gate A = ผ่านเกณฑ์ด่าน 1–2 ในหัวข้อ 11.2 (backtest + paper 4 สัปดาห์) ส่วน Gate B = ทำ Phase 7 ครบแล้วจึงเปิด live ด้วยทุน 5–10% ระหว่างรอ paper ครบ 4 สัปดาห์ ทำ Phase 4–6 คู่ขนานได้

### 13.1 โครงสร้าง repo

```
softtrade/
├─ CLAUDE.md            # กฎโปรเจกต์สำหรับ Claude Code (หลักการ 5 ข้อในหัวข้อ 1 + คำสั่ง test/lint)
├─ docs/SPEC.md         # เอกสารนี้
├─ docker-compose.yml
├─ backend/
│  ├─ app/api/          # FastAPI routers, ws
│  ├─ app/core/         # config, security, db, redis
│  ├─ app/exchange/     # ExchangeAdapter: binance_live, binance_testnet, simulated
│  ├─ app/marketdata/   # ws ingest, backfill, indicators
│  ├─ app/strategies/   # regime.py, s1_trend.py, s2_meanrev.py, s3_breakout.py, s4_grid.py, scoring.py
│  ├─ app/risk/         # sizing.py, limits.py, breakers.py, checks.py
│  ├─ app/execution/    # order_manager.py, reconciler.py
│  ├─ app/ai/           # llm_analyst.py, news.py, ml_model.py, prompts/
│  ├─ app/backtest/     # engine.py, walkforward.py, montecarlo.py
│  ├─ services/         # entrypoint แต่ละ service
│  └─ tests/
└─ frontend/
   ├─ src/ui/           # design system components (หัวข้อ 9.4)
   ├─ src/features/     # dashboard, trade, bots, ai, backtest, settings
   ├─ src/lib/          # api client (generated), ws client, formatters
   └─ src/styles/tokens.css
```

### 13.2 เฟสและ prompt

**Phase 0 — Scaffold**

```
อ่าน docs/SPEC.md ทั้งหมด แล้วสร้างโครง repo ตามหัวข้อ 13.1 พร้อม docker-compose (postgres+timescaledb, redis, api, frontend),
backend เป็น Python ล้วน (หัวข้อ 6) ด้วย uv + FastAPI + SQLAlchemy async + Alembic, frontend ด้วย Vite React TS + Tailwind v4,
ruff/mypy/pytest/eslint และ GitHub Actions CI เขียน CLAUDE.md สรุปหลักการหัวข้อ 1 และคำสั่งที่ใช้บ่อย
ยังไม่ต้องเขียน business logic จบเฟสเมื่อ `docker compose up` แล้ว /health ตอบ 200 และ CI ผ่าน
```

**Phase 1 — Market data + DB**

```
ทำตาม SPEC.md หัวข้อ 7 และ 8.3: สร้าง migration ทุกตาราง, ExchangeAdapter interface,
service market-data ที่รับ kline/bookTicker จาก Binance combined streams เก็บลง candles hypertable และ publish ลง Redis Streams,
คำสั่ง backfill ประวัติ 3 ปี (เคารพ rate limit), auto-reconnect + เติมแท่งที่หาย และโมดูล indicators
เขียน test ที่เทียบ indicator กับค่าอ้างอิง และ test การเติมแท่งที่หาย
```

**Phase 2 — Strategies + Backtester**

```
ทำตาม SPEC.md หัวข้อ 2 และ 11: regime detector, S1–S4 เป็น pure function (candles + state -> Signal),
scoring ที่รับ S_ml/S_ai เป็น input (ตอนนี้ใส่ 50), event-driven backtester ผ่าน SimulatedExchangeAdapter
พร้อมค่าธรรมเนียม/slippage/funding, walk-forward, Monte Carlo และ CLI `softtrade backtest --strategy s1 --symbol BTCUSDT`
ห้ามมี look-ahead bias: เขียน test ที่พิสูจน์ว่าสัญญาณที่แท่ง t ไม่เปลี่ยนเมื่อเพิ่มข้อมูลหลัง t
```

**Phase 3 — Risk Engine + Execution (Testnet)**

```
ทำตาม SPEC.md หัวข้อ 3 และ 8.3 ทุกข้อ: position sizing, exposure limits, circuit breakers, kill switch, pre-trade checklist,
order manager (idempotent clientOrderId, วาง OCO/Algo stop ทันทีหลัง fill, ปิดสถานะถ้าวาง stop ไม่ได้ใน 3 วินาที),
user data stream, reconciler ทุก 60 วินาที รันบน Binance Spot Testnet เท่านั้น
Risk Engine ต้องมี unit + property test (hypothesis) coverage ≥ 95% และ test จำลอง API error, 429, stale data, เน็ตหลุด
```

**Phase 4 — Design system + Dashboard**

```
ทำตาม SPEC.md หัวข้อ 9 และ 10.1 โดยดูไฟล์ design/Neumorphic_Trading_Dashboard.pdf ประกอบ:
สร้าง tokens.css (light + dark) ใช้ค่าสีตามตาราง 9.1 ทุกตัว (ไม่ดูดสีจาก PDF), component ทุกตัวใน 9.4 พร้อมหน้า /dev/ui ไว้ดู component, app shell (icon rail + header)
และหน้า Dashboard ที่ต่อ API/WebSocket จริง (generate type จาก OpenAPI) ทุกการ์ดมี loading/empty/error state
ตรวจ contrast ตาม WCAG AA และให้หน้าจอเหมือนไฟล์แบบที่ความกว้าง 1440 px
```

**Phase 5 — Bots, Trade, Backtest Lab, Risk & Settings**

```
ทำหน้า 2–4, 6, 7 ตาม SPEC.md หัวข้อ 10: wizard สร้างบอท 4 ขั้น, Bot detail พร้อม signal drawer แสดงคะแนนและผล risk check,
Backtest Lab เรียก job queue, หน้า Risk & Settings (API key พร้อม verify, TOTP, Telegram)
บังคับกฎหัวข้อ 11: ปุ่ม Go live ใช้ได้เมื่อ backtest และ paper ผ่านเกณฑ์เท่านั้น
```

**Phase 6 — AI layer**

```
ทำตาม SPEC.md หัวข้อ 4: news ingest + จัดหมวดด้วย claude-haiku-5-5, market brief ด้วย claude-sonnet-5-5 (structured output + Pydantic validate,
timeout -> S_ai=50), AI Chat แบบ SSE ที่มี tool read-only เท่านั้น, pipeline ML (triple-barrier label, LightGBM, purged walk-forward CV,
MLflow, PSI drift) และหน้า AI Analyst บันทึกทุก call ลง ai_analyses พร้อม cost
เพิ่ม test กัน prompt injection จากเนื้อข่าว
```

**Phase 7 — Hardening + Go live**

```
ทำตาม SPEC.md หัวข้อ 6.3 และ 12: envelope encryption ของ API key, log redaction, audit log, Prometheus metrics + Grafana dashboard,
Sentry, แจ้งเตือน Telegram, backup, CLI `softtrade kill` และ runbook สำหรับเหตุการณ์ (exchange ล่ม, key หลุด, DD ถึง kill)
ทำ security review ทั้ง repo และสรุปจุดเสี่ยงก่อนเปิด live ด้วยทุนเล็ก
```

**เคล็ดลับการสั่ง Claude Code:** ให้เริ่มแต่ละเฟสด้วยประโยค "วางแผนก่อนแล้วรอฉันอนุมัติ" และจบด้วย "รัน test ทั้งหมดแล้วสรุปสิ่งที่เปลี่ยน" ส่วนงานในเฟส 3 ควรอ่าน code review เองทุกบรรทัดก่อนใช้เงินจริง

## 14. ข้อควรระวังและคำเตือนความเสี่ยง

ไม่มีกลยุทธ์ไหนรับประกันกำไร และ AI ไม่ได้ทำให้ความเสี่ยงหายไป เอกสารนี้เป็นสเปกทางเทคนิค ไม่ใช่คำแนะนำการลงทุน ใช้เงินที่เสียได้เท่านั้น

- **Overfitting คือศัตรูอันดับ 1:** กลยุทธ์ที่ backtest สวยเกินจริง (Sharpe > 3, แทบไม่มี drawdown) มักพังใน live ให้เชื่อผล out-of-sample และ paper มากกว่า
- **ค่าธรรมเนียมกินกำไร:** ยิ่ง timeframe สั้น ค่าธรรมเนียม + slippage ยิ่งเป็นสัดส่วนใหญ่ของกำไร จึงเน้น 1H–4H และ limit order
- **ความเสี่ยงจาก exchange (counterparty):** เงินที่ฝากไว้บน exchange อาจได้รับผลกระทบจากเหตุการณ์ด้านความปลอดภัย เช่น ปลายตุลาคม 2026 ก.ล.ต. ต้องประเมินความเสี่ยงหลังเหตุการณ์ไซเบอร์ของแพลตฟอร์ม Binance ต่างประเทศ ([Nation Thailand](https://www.nationthailand.com/business/investment/40072935)) จึงควรเก็บเงินบน exchange เท่าที่บอทใช้จริง
- **กฎหมายไทย:** ก.ล.ต. เดินหน้าปิดกั้นแพลตฟอร์มสินทรัพย์ดิจิทัลต่างประเทศที่ชักชวนผู้ลงทุนไทยโดยไม่มีใบอนุญาต ([มิติหุ้น](https://www.mitihoon.com/2025/04/15/536453)) และยกระดับการดำเนินคดีต่อเนื่องในปี 2026 ([Tilleke & Gibbins](https://www.tilleke.com/insights/thai-sec-heightens-enforcement-against-cross-border-digital-asset-platforms/?page=20)) ก่อนใช้ Binance.com ให้ตรวจสถานะทางกฎหมายล่าสุด หรือพิจารณา exchange ที่ได้รับอนุญาตในไทย (เช่น Binance TH) ซึ่งต้องเช็กว่ามี API ที่บอทใช้ได้ครบไหม ออกแบบ `ExchangeAdapter` ให้เพิ่ม exchange อื่นได้ภายหลัง
- **ภาษี:** กำไรจากคริปโตอาจมีภาระภาษี ระบบควร export ประวัติเทรดเป็น CSV ได้ และควรปรึกษาผู้เชี่ยวชาญภาษี
- **Futures และเลเวอเรจ:** เปิดหลัง Spot ผ่านครบ 3 ด่านแล้วเท่านั้น เพราะความผิดพลาดในโค้ดขยายความเสียหายตามเลเวอเรจ
- **API เปลี่ยนบ่อย:** Binance ปรับ API หลายครั้งต่อปี (เช่น user data stream, algo order) ให้ subscribe changelog และมี integration test กับ testnet ใน CI ทุกสัปดาห์
