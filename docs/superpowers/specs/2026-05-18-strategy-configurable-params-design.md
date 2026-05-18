# Strategy Configurable Params Design

**Date:** 2026-05-18
**Scope:** Make RSI and MA Cross strategy params configurable via API and UI

---

## Problem

- `buildStrategy` in `manager.go` hardcodes RSI params `(14, 30, 70)` and ignores `strategy_params`
- MA Cross backend already reads `fast`/`slow` from `strategy_params`, but frontend has no input fields
- Users cannot tune strategy params without changing source code

---

## Solution

### Backend — `internal/runtime/manager.go`

Update `buildStrategy` RSI case to read from `strategy_params` using the existing `paramInt`/`paramDecimal` helpers (same pattern as MA Cross):

| Param | Key | Default |
|---|---|---|
| Period | `period` | 14 |
| Oversold | `oversold` | 30 |
| Overbought | `overbought` | 70 |

No other backend changes needed.

### Frontend — `StrategyParamFields` component

New component `src/pages/bot-control/StrategyParamFields.tsx`:
- Rendered below `StrategyPicker` in `BotControlPage`
- Conditionally renders fields based on selected strategy:
  - **MA Cross**: Fast Period (default 9), Slow Period (default 21)
  - **RSI**: Period (default 14), Oversold (default 30), Overbought (default 70)
- Values wired into `strategy_params` map in `StartRequest`

### Frontend — `BotControlPage` / `StartRequest` schema

- `DEFAULTS` updated to include `strategy_params` with correct defaults per strategy
- Zod schema updated to include `strategy_params: Record<string, string>`
- On strategy change, reset `strategy_params` to new strategy's defaults

---

## Out of Scope

- AI strategy params (deferred)
- Generic key-value UI for arbitrary params
- Backend validation of param ranges (rely on strategy constructors clamping)
