# Backtest KPI Card — NET PROFIT Hero Cell

**Date:** 2026-05-16
**File affected:** `apps/frontend/src/pages/backtest/BacktestMetricsCards.tsx`

## Problem

The absolute dollar profit/loss from a backtest is not prominently visible. `initial_equity` and `final_equity` are buried in a small footnote line at the bottom of the KPI card; the only top-line number is `total_return` as a percentage. Users cannot quickly see "I made/lost $X."

## Goal

Add a **NET PROFIT** cell as the first (visually prominent) metric in the KPI Summary card, showing the absolute dollar gain/loss with supporting context. No new components, no API changes.

## Design

### Cell content

Label: `NET PROFIT`

| Element | Value | Style |
|---|---|---|
| Headline | `+$842.00` | `fontSize: 22`, `fontWeight: 600`, `success.main` / `error.main` |
| Sub-line 1 | `$10,000 → $10,842` | `fontSize: 11`, `color: text.secondary` |
| Sub-line 2 | `+8.42%` | `fontSize: 11`, `color: text.secondary` |

**Derivation:**
- Headline: `Number(final_equity) - Number(initial_equity)`, formatted with sign prefix (`+` / `-`) and 2 decimal places
- Sub-line 1: `${initial_equity} → ${final_equity}` (raw strings from API, already 2 dp)
- Sub-line 2: `(Number(total_return) * 100).toFixed(2)%` with sign prefix — same value as the existing `TOTAL RETURN` cell, used here only as supporting context

The `TOTAL RETURN` percentage cell is retained unchanged; the sub-line `%` on the NET PROFIT cell is supporting context, not a replacement.

Color logic: same `returnColor()` helper already used by `TOTAL RETURN`.

### Grid layout

Current: `xs: "1fr 1fr", sm: "repeat(3, 1fr)", md: "repeat(6, 1fr)"` (6 cells)

Updated for 7 cells:

```ts
gridTemplateColumns: {
  xs: "1fr 1fr",
  sm: "repeat(3, 1fr)",
  md: "repeat(4, 1fr)",
  lg: "repeat(7, 1fr)",
}
```

All cells use the same `1fr` width. The NET PROFIT cell is visually distinguished by its larger font size (`fontSize: 22`) rather than a wider column.

### Footnote cleanup

The current footnote:
```
Bars processed: 1024 · Initial equity: 10000 · Final equity: 10842
```

Becomes:
```
Bars processed: 1024
```

`Initial equity` and `Final equity` are removed since they are now visible in the NET PROFIT cell. The date range lines below the footnote are unchanged.

## Scope

- **One file changed:** `BacktestMetricsCards.tsx`
- **No API changes** — all required data (`initial_equity`, `final_equity`, `metrics.total_return`) is already present in `BacktestResult`
- **No new components** — the NET PROFIT cell is an inline `Box` in the existing grid, following the same pattern as the other 6 cells
- The `BacktestComparisonTable` (multi-symbol view) is out of scope — it already shows `total_return` as the headline column and serves a different purpose (symbol comparison, not absolute P/L)

## Out of scope

- Per-trade P/L breakdown enhancements
- Multi-symbol comparison table changes
- Mobile-specific layout beyond the responsive grid breakpoints above
