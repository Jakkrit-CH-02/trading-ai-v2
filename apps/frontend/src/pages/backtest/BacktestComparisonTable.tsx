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
