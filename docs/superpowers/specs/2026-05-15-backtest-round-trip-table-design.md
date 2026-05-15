# Backtest Trade Table — Round-Trip Design

**Date:** 2026-05-15
**Scope:** Frontend only (`apps/frontend/src/pages/backtest/BacktestTradeTable.tsx`)

## Problem

The current trade table renders one row per raw order (BUY and SELL separately). Users cannot easily see the purchase price, sale price, and net profit of a single trade at a glance.

## Goal

Merge paired BUY+SELL orders into a single round-trip row showing entry price, exit price, qty, and net P/L. Open trades (BUY without a matching SELL) are shown with `—` in exit columns and an "Open" status chip.

## Approach

Frontend-only pairing. Walk `trades[]` sequentially, match each BUY with the next SELL, and produce a `RoundTrip[]` array to render. No backend changes required. Safe because the backtest engine is strictly long-only and always alternates BUY → SELL.

## Data model (frontend only)

```ts
interface RoundTrip {
  id: string;             // BUY order_id (stable key)
  entryTimeMs: number;
  entryPrice: string;
  exitTimeMs: number | null;
  exitPrice: string | null;
  qty: string;
  pl: string | null;      // null = open
}
```

Pairing logic: iterate `trades[]`, push BUY into a pending slot; when a SELL is seen, close the pending slot and emit a `RoundTrip`. Any BUY still pending at the end of the array emits as an open round-trip.

## Table columns

| Column | Value | Notes |
|---|---|---|
| # | 1-based index | |
| Entry Time (UTC) | `entryTimeMs` formatted | |
| Entry Price | `entryPrice` | string decimal |
| Exit Time (UTC) | `exitTimeMs` formatted | `—` if open |
| Exit Price | `exitPrice` | `—` if open |
| Qty | `qty` | |
| P/L | `pl` | `—` if open; green if > 0, red if < 0 |
| Status | Chip | `Closed` (default color) / `Open` (warning color) |

`Reason` column is dropped.

## Component changes

- `BacktestTradeTable.tsx`: add `pairTrades(trades: BacktestTrade[]): RoundTrip[]` pure function and update the render to use `RoundTrip[]`.
- Trade count in card title reflects round-trips: `Trades (N)` where N = `roundTrips.length`.
- No changes to `src/api/backtest.ts` or any backend file.

## Out of scope

- Pyramiding / partial fills (not supported by the engine today)
- Sorting or filtering round-trips
- Linking to the equity chart
