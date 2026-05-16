# Backtest — NET PROFIT Display

**Date:** 2026-05-16
**Files affected:**
- `apps/frontend/src/pages/backtest/BacktestMetricsCards.tsx`
- `apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx`

## Problem

The absolute dollar profit/loss from a backtest is not prominently visible in either view:
- **Single-symbol:** `initial_equity` and `final_equity` are buried in a small footnote line; the only top-line number is `total_return` as a percentage.
- **Multi-symbol:** `BacktestComparisonTable` shows no absolute dollar figure at all — only `total_return` as a percentage per symbol.

Users cannot quickly see "I made/lost $X" in either view.

## Goal

Show the absolute dollar net profit prominently in both the single-symbol KPI card and the multi-symbol comparison table. No new components, no API changes.

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

## BacktestComparisonTable — NET PROFIT column

Add a `NET PROFIT` column as the second column (after SYMBOL, before TOTAL RETURN) in the multi-symbol comparison table.

| Element | Value | Style |
|---|---|---|
| Cell value | `+$842.00` | `fontWeight: 600`, `success.main` / `error.main` |

**Derivation:** `Number(r.final_equity) - Number(r.initial_equity)`, formatted with sign prefix and 2 decimal places.

The column is sortable via `TableSortLabel`, following the same `SortKey` pattern used by the existing columns. Add `"net_profit"` to the `SortKey` union type; sorting computes the net profit value at sort time (no pre-computation needed).

The existing `TOTAL RETURN` column is retained — it stays as a percentage for quick relative comparison across symbols.

## Scope

- **Two files changed:** `BacktestMetricsCards.tsx`, `BacktestComparisonTable.tsx`
- **No API changes** — all required data (`initial_equity`, `final_equity`, `metrics.total_return`) is already present in `BacktestResult`
- **No new components** — all changes are inline within existing files

## Out of scope

- Per-trade P/L breakdown enhancements
- Mobile-specific layout beyond the responsive grid breakpoints above
