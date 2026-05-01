# Workflow: ทำงานกับ Claude Code อย่างประหยัด token และตรงเป้า

ไฟล์นี้เขียนให้ **คุณ** อ่าน ไม่ได้ให้ Claude อ่าน เป็นวิธีคิดและ template prompt ที่ใช้ซ้ำได้

## หลักคิด 4 ข้อ

1. **CLAUDE.md ทำงานแทน prompt ซ้ำๆ** — สิ่งที่ "เปลี่ยนยาก" (tech stack, naming, risk policy) เขียนใน CLAUDE.md ครั้งเดียว ไม่ต้อง paste ในทุก prompt
2. **Requirement = WHAT, code structure = HOW** — ไม่ต้อง generate design doc ระหว่างทาง requirement ที่คุณมีอยู่แล้วคือ source of truth ของ "ต้องทำอะไร"
3. **Vertical slice เล็กกว่าที่คิด** — slice ที่ดีคือ "เปิดเครื่อง รัน เห็นผล" ใน 1 รอบ เช่น "frontend ปุ่ม Start ส่งคำสั่งไป backend แล้ว backend log ว่ารับคำสั่ง" ไม่ใช่ "ทำ bot control feature ครบ"
4. **Test เขียนก่อน code** — โดยเฉพาะใน `risk/` และ `strategy/` ให้คุณเขียน test case ที่อยากให้ผ่าน แล้วค่อยให้ Claude เขียน implementation

---

## วงจร 1 slice (loop ที่ใช้ซ้ำทุกครั้ง)

```
1. คุณ:  เลือก slice ถัดไป (ดู VERTICAL_SLICE_*.md หรือ requirement file)
2. คุณ:  เขียน acceptance criteria 3-5 ข้อใส่ในไฟล์ slice (หรือ TODO ในรูทโปรเจกต์)
3. คุณ:  ระบุไฟล์ที่จะแตะ (เปิดให้ Claude ดู)
4. Claude: implement (ไม่ต้องอ่านทั้งโปรเจกต์)
5. คุณ:  รัน test + manual verify
6. คุณ:  commit แล้วเริ่มใหม่
```

**กฎเหล็ก:** ทุก slice ต้องจบใน 1 session ของ Claude ถ้าจบไม่ได้ slice ใหญ่ไป — แบ่งครึ่งใหม่

---

## Prompt templates ที่ใช้บ่อย

### Template 1 — เริ่ม slice ใหม่

```
ฉันจะทำ slice: <ชื่อ slice>

Requirement: ../trading_bot_requirements_v2/backend-go/05_strategy_engine.md
ไฟล์ที่จะแตะ:
- apps/backend-go/internal/strategy/engine.go (สร้างใหม่)
- apps/backend-go/internal/strategy/builtin/ma_cross.go (สร้างใหม่)
- apps/backend-go/internal/strategy/engine_test.go (สร้างใหม่)

Acceptance criteria:
1. Engine.OnBar(bar) คืน Signal{BUY|SELL|HOLD, reason, timestamp}
2. MA cross 9/21 — BUY เมื่อ fast cross above slow, SELL เมื่อ cross below
3. Test: 3 cases (cross up, cross down, no cross) ต้องผ่าน
4. ไม่แตะไฟล์อื่นนอกจากที่ระบุ

อ่าน CLAUDE.md และ apps/backend-go/CLAUDE.md ก่อนเริ่ม
```

ทำไมถึงดี:
- ระบุไฟล์ชัดเจน → Claude ไม่เผลออ่านทั้ง repo
- Acceptance criteria เป็น checklist → verify ง่าย
- ผูก requirement file → ไม่ต้อง paste เนื้อหา requirement ทั้งหมด

### Template 2 — ขอ test ก่อน implementation (test-as-spec)

```
อ่าน apps/backend-go/internal/risk/checks.go (ยังไม่มี implementation)

เขียนแค่ apps/backend-go/internal/risk/checks_test.go ก่อน
ครอบคลุม case:
- Position size > 2% ของ equity → reject ด้วย ErrPositionTooLarge
- Order ไม่มี stop loss → reject ด้วย ErrStopLossRequired  
- Slippage estimate > 30bps → reject ด้วย ErrSlippageExceeded
- Order ปกติ → pass

ห้ามเขียน implementation ตอนนี้ ฉันจะ review test ก่อน
```

หลัง review test แล้ว:

```
OK test ผ่าน review แล้ว ตอนนี้ implement apps/backend-go/internal/risk/checks.go ให้ test ทั้งหมดผ่าน
ห้ามแก้ test ห้ามเพิ่ม case ใหม่
```

### Template 3 — เพิ่มหน้า frontend

```
สร้างหน้า bot-control ตาม
- requirement: ../trading_bot_requirements_v2/frontend/03_bot_control.md
- frontend convention: apps/frontend/CLAUDE.md

โครงสร้าง:
apps/frontend/src/pages/bot-control/
├── BotControlPage.tsx
├── components/
│   ├── ModeSelector.tsx
│   ├── StrategyPicker.tsx
│   └── LiveConfirmModal.tsx
└── hooks/
    └── useBotControl.ts

ใช้ TanStack Query สำหรับ /api/bot/status (poll ทุก 2 วินาที)
ใช้ react-hook-form + zod สำหรับฟอร์ม
ปุ่ม Start เมื่อ mode = live ต้องเปิด LiveConfirmModal

อย่าลืม sx prop only
```

### Template 4 — Bug fix

```
Bug: เมื่อ frontend เรียก POST /api/bot/start แล้ว backend คืน 500

อ่านเฉพาะ:
- apps/backend-go/internal/api/handlers/bot.go
- apps/backend-go/internal/runtime/controller.go
- log ข้างล่างนี้:

<paste log ที่ error>

หาสาเหตุก่อน อย่าแก้ทันที — บอกฉันสิ่งที่เจอ + เสนอ 2 วิธีแก้
```

ทำไมถึงดี:
- จำกัดไฟล์ที่อ่าน → token ไม่บาน
- บังคับให้ analyze ก่อน fix → Claude ไม่ "แก้ๆไปก่อน"

### Template 5 — Refactor (อันตราย ระวัง)

```
Refactor: ย้าย logic การ validate API key จาก internal/api/handlers/bot.go ไป internal/auth/validator.go

ขอบเขต:
- ไฟล์ที่แตะได้: handlers/bot.go, auth/validator.go, auth/validator_test.go
- ห้ามแตะ: handlers อื่น, runtime/, strategy/

ก่อน refactor: รัน `go test ./internal/auth ./internal/api` แล้วบอกผล baseline
หลัง refactor: รันอีกครั้ง ผลต้องเหมือนเดิม
```

---

## Anti-patterns (อย่าทำ)

### ❌ "ดูทั้ง repo แล้วบอกว่าควรปรับอะไร"
ปัญหา: token พุ่ง, คำตอบจะเป็นความเห็นทั่วไปที่ไม่ actionable
แก้: ถามคำถามเฉพาะเจาะจง เช่น "ดูเฉพาะ internal/risk/ มี duplicate logic ไหม"

### ❌ "ทำ feature X ให้สมบูรณ์"
ปัญหา: "สมบูรณ์" คลุมเครือ, slice ใหญ่เกิน, verify ยาก
แก้: แตกเป็น 3-5 slice ที่แต่ละอันรันได้

### ❌ "เขียน design doc ก่อน implement"
ปัญหา: design doc ที่ไม่มีคนอ่านคือ token ทิ้ง
แก้: เขียน test case + module signature แทน

### ❌ "Generate code ทั้ง 30 requirement พร้อมกัน"
ปัญหา: ไม่มีทาง verify ได้, dependency พัวพัน, fix ยาก
แก้: vertical slice ทีละชิ้น

### ❌ paste log/code ยาวๆ ลง prompt โดยไม่ตัด
ปัญหา: Claude อ่าน noise มากกว่า signal
แก้: ตัดเฉพาะ stack trace ที่เกี่ยวข้อง 20-30 บรรทัด

---

## เคล็ดลับประหยัด token

1. **ใช้ relative path** เสมอเวลา reference ไฟล์ — Claude resolve ได้และสั้นกว่า
2. **อย่า paste requirement file** — ให้ link path ไป Claude ไปอ่านเองถ้าต้องการ
3. **ใช้ slash command** สำหรับงานซ้ำ (ดู `commands/`)
4. **Commit บ่อย** — session ใหม่ Claude เริ่มจาก state ที่ commit แล้ว ไม่ต้องเล่าอดีต
5. **ใส่ context ครั้งเดียวใน CLAUDE.md** — แก้ CLAUDE.md ดีกว่า repeat ใน prompt

## เมื่อไหร่แก้ CLAUDE.md vs ใน prompt

| เปลี่ยนถาวร | เขียนใน CLAUDE.md |
|---|---|
| ใช้ครั้งเดียว | เขียนใน prompt |
| ใช้ในงาน frontend อย่างเดียว | `apps/frontend/CLAUDE.md` |
| ใช้ทั้งระบบ | root `CLAUDE.md` |

ตัวอย่าง:
- "money เป็น Decimal" → root CLAUDE.md ✅ (ใช้ทั้งระบบ ถาวร)
- "หน้า dashboard refresh ทุก 2 วินาที" → frontend.CLAUDE.md ✅
- "วันนี้เพิ่มปุ่ม Reset" → prompt ❌ (ใช้ครั้งเดียว)

---

## Live trading: ขั้นสุดท้าย ไม่ใช่ขั้นแรก

**ห้าม** prompt ให้ Claude ทำ live trading ก่อนผ่านขั้นนี้ครบ:

- ☐ Backtest engine ผ่าน fixture candles ได้ผลสมเหตุสมผล
- ☐ Paper trade รันบน Binance testnet ได้ ≥ 24 ชั่วโมงไม่ crash
- ☐ Risk engine reject case ที่ควร reject ในการทดสอบ
- ☐ Kill switch ทดสอบแล้วทำงาน (cancel orders + flatten)
- ☐ Monitoring + alerts ใช้งานได้
- ☐ คุณเองเข้าใจทุก signal ที่ระบบสร้าง

ถ้ายังไม่ครบทั้ง 6 — `LIVE_TRADING_ENABLED=false` คาเครื่องไว้
