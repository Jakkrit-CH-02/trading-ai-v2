# Backtest NET PROFIT Display Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show absolute dollar net profit prominently in both the single-symbol KPI card and the multi-symbol comparison table on the backtest page.

**Architecture:** Two self-contained component edits — `BacktestMetricsCards.tsx` gains a NET PROFIT hero cell (first in the KPI grid) and `BacktestComparisonTable.tsx` gains a sortable NET PROFIT column (second column, after SYMBOL). Each change exports a pure helper function that is unit-tested independently. No API or backend changes.

**Tech Stack:** React 18, TypeScript strict, MUI v5 (`sx` only), vitest, `@testing-library/react` (not needed — pure function tests only)

---

## File Map

| File | Change |
|---|---|
| `apps/frontend/src/pages/backtest/BacktestMetricsCards.tsx` | Export `netProfitAbs` helper; add NET PROFIT hero cell; update grid breakpoints; trim footnote |
| `apps/frontend/src/pages/backtest/BacktestMetricsCards.test.ts` | Create — unit tests for `netProfitAbs` |
| `apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx` | Export `computeNetProfit` helper; add `"net_profit"` sort key; add NET PROFIT column header + cell |
| `apps/frontend/src/pages/backtest/BacktestComparisonTable.test.ts` | Create — unit tests for `computeNetProfit` |

---

## Task 1: BacktestMetricsCards — NET PROFIT hero cell

**Files:**
- Modify: `apps/frontend/src/pages/backtest/BacktestMetricsCards.tsx`
- Create: `apps/frontend/src/pages/backtest/BacktestMetricsCards.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/frontend/src/pages/backtest/BacktestMetricsCards.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { netProfitAbs } from "./BacktestMetricsCards";

describe("netProfitAbs", () => {
  it("returns positive profit when final > initial", () => {
    expect(netProfitAbs("10000", "10842")).toBeCloseTo(842);
  });

  it("returns negative profit when final < initial", () => {
    expect(netProfitAbs("10000", "9500")).toBeCloseTo(-500);
  });

  it("returns zero when equity is unchanged", () => {
    expect(netProfitAbs("10000", "10000")).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/frontend && pnpm exec vitest run src/pages/backtest/BacktestMetricsCards.test.ts
```

Expected: FAIL — `netProfitAbs` is not exported from `BacktestMetricsCards`.

- [ ] **Step 3: Implement the changes to BacktestMetricsCards.tsx**

Replace the full content of `apps/frontend/src/pages/backtest/BacktestMetricsCards.tsx` with:

```tsx
import { Alert, Box, Card, CardContent, Typography } from "@mui/material";
import type { BacktestMetrics, BacktestResult } from "../../api/backtest";
import { formatTime } from "../../lib/format";

export interface BacktestMetricsCardsProps {
  result: BacktestResult;
}

export function netProfitAbs(initialEquity: string, finalEquity: string): number {
  return Number(finalEquity) - Number(initialEquity);
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: {
      xs: "1fr 1fr",
      sm: "repeat(3, 1fr)",
      md: "repeat(4, 1fr)",
      lg: "repeat(7, 1fr)",
    },
  },
  cell: { display: "flex", flexDirection: "column", gap: 0.5 },
  label: { color: "text.secondary", fontSize: 12, letterSpacing: 0.5 },
  value: { fontSize: 18, fontWeight: 600 },
  heroValue: { fontSize: 22, fontWeight: 600 },
  subLine: { fontSize: 11, color: "text.secondary" },
} as const;

function pct(decimalString: string): string {
  const n = Number(decimalString);
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

function num(decimalString: string, digits = 2): string {
  const n = Number(decimalString);
  if (!Number.isFinite(n)) return "—";
  return n.toFixed(digits);
}

function returnColor(decimalString: string): string {
  const n = Number(decimalString);
  if (!Number.isFinite(n) || n === 0) return "text.primary";
  return n > 0 ? "success.main" : "error.main";
}

export default function BacktestMetricsCards(props: BacktestMetricsCardsProps) {
  const { result } = props;
  const m: BacktestMetrics = result.metrics;
  const requestedFrom = result.config.from_ms;
  const requestedTo = result.config.to_ms;
  const actualFrom = result.start_ms;
  const actualTo = result.end_ms;
  const fromClamped = requestedFrom != null && requestedFrom < actualFrom;
  const toClamped = requestedTo != null && requestedTo > actualTo;
  const showRangeWarning = fromClamped || toClamped;

  const np = netProfitAbs(result.initial_equity, result.final_equity);
  const npColor =
    np > 0 ? "success.main" : np < 0 ? "error.main" : "text.primary";

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          KPI Summary
        </Typography>
        <Box sx={styles.grid}>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>NET PROFIT</Typography>
            <Typography sx={{ ...styles.heroValue, color: npColor }}>
              {np >= 0 ? "+" : ""}
              {np.toFixed(2)}
            </Typography>
            <Typography sx={styles.subLine}>
              ${result.initial_equity} → ${result.final_equity}
            </Typography>
            <Typography sx={styles.subLine}>
              {Number(m.total_return) >= 0 ? "+" : ""}
              {(Number(m.total_return) * 100).toFixed(2)}%
            </Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>TOTAL RETURN</Typography>
            <Typography sx={{ ...styles.value, color: returnColor(m.total_return) }}>
              {pct(m.total_return)}
            </Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>WIN RATE</Typography>
            <Typography sx={styles.value}>{pct(m.win_rate)}</Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>PROFIT FACTOR</Typography>
            <Typography sx={styles.value}>{num(m.profit_factor)}</Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>MAX DRAWDOWN</Typography>
            <Typography sx={{ ...styles.value, color: "error.main" }}>
              {pct(m.max_drawdown)}
            </Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>SHARPE</Typography>
            <Typography sx={styles.value}>{num(m.sharpe_ratio)}</Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>TRADES</Typography>
            <Typography sx={styles.value}>
              {m.total_trades}{" "}
              <Typography component="span" sx={{ fontSize: 12, color: "text.secondary" }}>
                ({m.winning_trades}W / {m.losing_trades}L)
              </Typography>
            </Typography>
          </Box>
        </Box>
        <Box sx={{ mt: 2, color: "text.secondary", fontSize: 12 }}>
          Bars processed: {result.bars_processed}
        </Box>
        <Box sx={{ mt: 2, display: "flex", flexDirection: "column", gap: 0.75 }}>
          <Typography sx={{ color: "text.secondary", fontSize: 12 }}>
            Requested range:{" "}
            {requestedFrom != null || requestedTo != null
              ? `${requestedFrom != null ? formatTime(requestedFrom) : "Earliest available"} to ${requestedTo != null ? formatTime(requestedTo) : "Latest available"}`
              : "Latest available bars"}
          </Typography>
          <Typography sx={{ color: "text.secondary", fontSize: 12 }}>
            Actual range used: {formatTime(actualFrom)} to {formatTime(actualTo)}
          </Typography>
        </Box>
        {showRangeWarning ? (
          <Alert severity="info" sx={{ mt: 2 }}>
            Historical data was only available for part of the requested window, so the
            backtest started from the earliest available bar in that range.
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

```bash
cd apps/frontend && pnpm exec vitest run src/pages/backtest/BacktestMetricsCards.test.ts
```

Expected: PASS — 3 tests pass.

- [ ] **Step 5: Typecheck**

```bash
cd apps/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 6: Commit**

```bash
git add apps/frontend/src/pages/backtest/BacktestMetricsCards.tsx \
        apps/frontend/src/pages/backtest/BacktestMetricsCards.test.ts
git commit -m "feat(backtest): add NET PROFIT hero cell to KPI Summary card"
```

---

## Task 2: BacktestComparisonTable — sortable NET PROFIT column

**Files:**
- Modify: `apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx`
- Create: `apps/frontend/src/pages/backtest/BacktestComparisonTable.test.ts`

- [ ] **Step 1: Write the failing test**

Create `apps/frontend/src/pages/backtest/BacktestComparisonTable.test.ts`:

```ts
import { describe, it, expect } from "vitest";
import { computeNetProfit } from "./BacktestComparisonTable";
import type { BacktestResult } from "../../api/backtest";

function makeResult(initial: string, final: string, symbol = "BTCUSDT"): BacktestResult {
  return {
    id: "test-id",
    config: {
      symbol,
      interval: "1h",
      strategy_name: "ma_crossover",
      initial_cash: initial,
      position_fraction: "0.1",
      stop_loss_pct: "0.02",
    },
    start_ms: 1000,
    end_ms: 2000,
    bars_processed: 100,
    initial_equity: initial,
    final_equity: final,
    metrics: {
      total_trades: 5,
      winning_trades: 3,
      losing_trades: 2,
      win_rate: "0.6",
      profit_factor: "1.5",
      total_return: "0.0842",
      max_drawdown: "0.05",
      sharpe_ratio: "1.2",
    },
    equity_curve: [],
    trades: [],
    created_ms: 3000,
  };
}

describe("computeNetProfit", () => {
  it("returns positive profit when final > initial", () => {
    expect(computeNetProfit(makeResult("10000", "10842"))).toBeCloseTo(842);
  });

  it("returns negative profit when final < initial", () => {
    expect(computeNetProfit(makeResult("10000", "9500"))).toBeCloseTo(-500);
  });

  it("returns zero when equity is unchanged", () => {
    expect(computeNetProfit(makeResult("10000", "10000"))).toBe(0);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd apps/frontend && pnpm exec vitest run src/pages/backtest/BacktestComparisonTable.test.ts
```

Expected: FAIL — `computeNetProfit` is not exported from `BacktestComparisonTable`.

- [ ] **Step 3: Implement the changes to BacktestComparisonTable.tsx**

Replace the full content of `apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx` with:

```tsx
import {
  Box,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from "@mui/material";
import { useState } from "react";
import type { BacktestResult } from "../../api/backtest";

export interface BacktestComparisonTableProps {
  results: BacktestResult[];
}

type SortKey =
  | "symbol"
  | "net_profit"
  | "total_return"
  | "win_rate"
  | "sharpe_ratio"
  | "max_drawdown"
  | "total_trades";

export function computeNetProfit(r: BacktestResult): number {
  return Number(r.final_equity) - Number(r.initial_equity);
}

const styles = {
  header: { fontWeight: 700, fontSize: 12, letterSpacing: 0.5, color: "text.secondary" },
} as const;

function pct(s: string): string {
  const n = Number(s);
  return Number.isFinite(n) ? `${(n * 100).toFixed(2)}%` : "—";
}

function num(s: string, digits = 2): string {
  const n = Number(s);
  return Number.isFinite(n) ? n.toFixed(digits) : "—";
}

export default function BacktestComparisonTable(
  props: BacktestComparisonTableProps,
) {
  const { results } = props;
  const [sortKey, setSortKey] = useState<SortKey>("net_profit");
  const [sortAsc, setSortAsc] = useState(false);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortAsc((prev) => !prev);
    } else {
      setSortKey(key);
      setSortAsc(false);
    }
  };

  const sorted = [...results].sort((a, b) => {
    if (sortKey === "symbol") {
      return sortAsc
        ? a.config.symbol.localeCompare(b.config.symbol)
        : b.config.symbol.localeCompare(a.config.symbol);
    }
    let va: number, vb: number;
    if (sortKey === "total_trades") {
      va = a.metrics.total_trades;
      vb = b.metrics.total_trades;
    } else if (sortKey === "net_profit") {
      va = computeNetProfit(a);
      vb = computeNetProfit(b);
    } else {
      va = Number(a.metrics[sortKey]);
      vb = Number(b.metrics[sortKey]);
    }
    return sortAsc ? va - vb : vb - va;
  });

  const col = (key: SortKey, label: string) => (
    <TableCell sx={styles.header}>
      <TableSortLabel
        active={sortKey === key}
        direction={sortKey === key ? (sortAsc ? "asc" : "desc") : "desc"}
        onClick={() => handleSort(key)}
      >
        {label}
      </TableSortLabel>
    </TableCell>
  );

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Symbol Comparison
        </Typography>
        <Box sx={{ overflowX: "auto" }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                {col("symbol", "SYMBOL")}
                {col("net_profit", "NET PROFIT")}
                {col("total_return", "TOTAL RETURN")}
                {col("win_rate", "WIN RATE")}
                {col("sharpe_ratio", "SHARPE")}
                {col("max_drawdown", "MAX DRAWDOWN")}
                {col("total_trades", "TRADES")}
              </TableRow>
            </TableHead>
            <TableBody>
              {sorted.map((r) => {
                const ret = Number(r.metrics.total_return);
                const retColor =
                  ret > 0 ? "success.main" : ret < 0 ? "error.main" : "text.primary";
                const np = computeNetProfit(r);
                const npColor =
                  np > 0 ? "success.main" : np < 0 ? "error.main" : "text.primary";
                return (
                  <TableRow key={r.config.symbol} hover>
                    <TableCell sx={{ fontWeight: 600 }}>
                      {r.config.symbol}
                    </TableCell>
                    <TableCell sx={{ color: npColor, fontWeight: 600 }}>
                      {np >= 0 ? "+" : ""}
                      {np.toFixed(2)}
                    </TableCell>
                    <TableCell sx={{ color: retColor, fontWeight: 600 }}>
                      {pct(r.metrics.total_return)}
                    </TableCell>
                    <TableCell>{pct(r.metrics.win_rate)}</TableCell>
                    <TableCell>{num(r.metrics.sharpe_ratio)}</TableCell>
                    <TableCell sx={{ color: "error.main" }}>
                      {pct(r.metrics.max_drawdown)}
                    </TableCell>
                    <TableCell>
                      {r.metrics.total_trades}{" "}
                      <Typography
                        component="span"
                        sx={{ fontSize: 11, color: "text.secondary" }}
                      >
                        ({r.metrics.winning_trades}W/{r.metrics.losing_trades}L)
                      </Typography>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      </CardContent>
    </Card>
  );
}
```

Note: the default sort key is changed from `"total_return"` to `"net_profit"` so the most prominent metric sorts first by default.

- [ ] **Step 4: Run test to verify it passes**

```bash
cd apps/frontend && pnpm exec vitest run src/pages/backtest/BacktestComparisonTable.test.ts
```

Expected: PASS — 3 tests pass.

- [ ] **Step 5: Run all backtest tests**

```bash
cd apps/frontend && pnpm exec vitest run src/pages/backtest/
```

Expected: all tests pass (BacktestMetricsCards, BacktestComparisonTable, BacktestTradeTable).

- [ ] **Step 6: Typecheck**

```bash
cd apps/frontend && pnpm typecheck
```

Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add apps/frontend/src/pages/backtest/BacktestComparisonTable.tsx \
        apps/frontend/src/pages/backtest/BacktestComparisonTable.test.ts
git commit -m "feat(backtest): add sortable NET PROFIT column to comparison table"
```
