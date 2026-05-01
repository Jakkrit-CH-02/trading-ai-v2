# `_flow/` — Lean Spec & Build Flow

โฟลเดอร์นี้คือ **คู่มือใช้งาน requirement ที่คุณมีอยู่แล้ว** ในการสร้างระบบจริงด้วย Claude Code โดยไม่ต้องผ่าน Spec Kit (ไม่ต้อง generate spec.md/plan.md/tasks.md/research.md/contracts/quickstart.md ซ้ำซ้อน)

แนวคิดสั้นๆ คือ:

1. **`requirement` (โฟลเดอร์ frontend/, backend-go/, ai-python/) = WHAT** — มีอยู่แล้วและไม่ต้องแตะ
2. **`CLAUDE.md` (ในโปรเจกต์จริง) = HOW + RULES** — context ถาวรที่ Claude Code จะอ่านทุกครั้ง
3. **Tests + Code structure = SPEC ที่ executable** — ไม่ต้องเขียน design doc แยก
4. **Vertical slice = หน่วยทำงาน** — สร้างทีละชิ้นที่ run ได้ end-to-end

---

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | ใช้เมื่อไหร่ | คัดลอกไปที่ไหน |
|---|---|---|
| `CLAUDE.md` | Claude อ่านทุก session | root ของ monorepo |
| `frontend.CLAUDE.md` | Claude อ่านเมื่อทำงาน frontend | `apps/frontend/CLAUDE.md` |
| `backend-go.CLAUDE.md` | Claude อ่านเมื่อทำงาน backend | `apps/backend-go/CLAUDE.md` |
| `ai-python.CLAUDE.md` | Claude อ่านเมื่อทำงาน AI service | `apps/ai-python/CLAUDE.md` |
| `STRUCTURE.md` | อ้างอิงเวลา scaffold ครั้งแรก | ไม่ต้องคัดลอก (ใช้เป็น reference) |
| `WORKFLOW.md` | คุณอ่านเอง — วิธี prompt และทำ slice | ไม่ต้องคัดลอก |
| `VERTICAL_SLICE_1.md` | Slice แรก: paper trade BTC/USDT MA cross | ใช้เป็นแผนงานชิ้นแรก |
| `commands/*.md` | Slash command templates | `.claude/commands/` |

---

## Quick Start

```bash
# 1. สร้างโปรเจกต์จริงเป็น sibling folder
cd /Users/teng/personal/app/trading-ai-v2
mkdir app && cd app

# 2. คัดลอก CLAUDE.md ไปวาง
cp ../trading_bot_requirements_v2/_flow/CLAUDE.md ./CLAUDE.md

# 3. Scaffold 3 services ตาม STRUCTURE.md
mkdir -p apps/frontend apps/backend-go apps/ai-python

# 4. คัดลอก sub-CLAUDE.md
cp ../trading_bot_requirements_v2/_flow/frontend.CLAUDE.md   apps/frontend/CLAUDE.md
cp ../trading_bot_requirements_v2/_flow/backend-go.CLAUDE.md apps/backend-go/CLAUDE.md
cp ../trading_bot_requirements_v2/_flow/ai-python.CLAUDE.md  apps/ai-python/CLAUDE.md

# 5. คัดลอก slash commands
mkdir -p .claude/commands
cp ../trading_bot_requirements_v2/_flow/commands/*.md .claude/commands/

# 6. เริ่ม slice แรก
# เปิด VERTICAL_SLICE_1.md อ่านลำดับ prompt แล้วยิงให้ Claude Code ทีละข้อ
```

---

## หลักการสำคัญ (อ่านครั้งเดียวจำให้ได้)

- **Claude อ่าน CLAUDE.md ทุก session อยู่แล้ว** ไม่ต้อง paste ซ้ำ — ใส่ context ที่ "เปลี่ยนยาก" ที่นั่น
- **อย่า prompt ให้ Claude generate plan.md ยาวๆ** ก่อนเขียน code — ให้ลงมือทันทีบน slice ที่เล็กพอจะ verify ได้ใน 1 รอบ
- **Test = spec** — เขียน test ก่อนแล้วให้ Claude ทำให้ผ่าน ดีกว่าเขียน design doc ที่ไม่มีใครอ่าน
- **อย่าให้ Claude อ่าน requirement ทั้งโฟลเดอร์** ในทุก prompt — link ไปไฟล์เดียวที่เกี่ยวข้องกับ slice ปัจจุบัน
- **Live trading = สวิตช์สุดท้าย** — ทุก slice ก่อนหน้าต้องผ่าน paper trade + backtest

---

## เปิดอ่านลำดับนี้

1. `WORKFLOW.md` — เข้าใจวิธีทำงานก่อน
2. `STRUCTURE.md` — ดูว่าโปรเจกต์จะมีหน้าตายังไง
3. `CLAUDE.md` + sub-CLAUDE — ดู context ที่ Claude จะมี
4. `VERTICAL_SLICE_1.md` — ลงมือ slice แรก
