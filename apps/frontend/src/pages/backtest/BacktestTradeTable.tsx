// apps/frontend/src/pages/backtest/BacktestTradeTable.tsx
import {
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { BacktestTrade } from "../../api/backtest";

export interface BacktestTradeTableProps {
  trades: BacktestTrade[];
}

interface RoundTrip {
  id: string;
  entryTimeMs: number;
  entryPrice: string;
  exitTimeMs: number | null;
  exitPrice: string | null;
  qty: string;
  pl: string | null;
}

export function pairTrades(trades: BacktestTrade[]): RoundTrip[] {
  const result: RoundTrip[] = [];
  let pending: BacktestTrade | null = null;
  for (const t of trades) {
    if (t.side.toUpperCase() === "BUY") {
      pending = t;
    } else if (t.side.toUpperCase() === "SELL" && pending !== null) {
      result.push({
        id: pending.order_id,
        entryTimeMs: pending.timestamp_ms,
        entryPrice: pending.price,
        exitTimeMs: t.timestamp_ms,
        exitPrice: t.price,
        qty: pending.qty,
        pl: t.realized_pl,
      });
      pending = null;
    }
  }
  if (pending !== null) {
    result.push({
      id: pending.order_id,
      entryTimeMs: pending.timestamp_ms,
      entryPrice: pending.price,
      exitTimeMs: null,
      exitPrice: null,
      qty: pending.qty,
      pl: null,
    });
  }
  return result;
}

const styles = {
  empty: { color: "text.secondary", textAlign: "center", py: 4 },
  cell: { whiteSpace: "nowrap" },
} as const;

function fmtTime(ms: number): string {
  return new Date(ms).toISOString().slice(0, 19).replace("T", " ");
}

function plColor(pl: string | null): string {
  if (pl === null) return "text.primary";
  const n = Number(pl);
  if (!Number.isFinite(n) || n === 0) return "text.primary";
  return n > 0 ? "success.main" : "error.main";
}

export default function BacktestTradeTable(props: BacktestTradeTableProps) {
  const { trades } = props;
  const roundTrips = pairTrades(trades);
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Trades ({roundTrips.length})
        </Typography>
        {roundTrips.length === 0 ? (
          <Typography sx={styles.empty}>No trades produced.</Typography>
        ) : (
          <TableContainer sx={{ maxHeight: 480 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={styles.cell}>#</TableCell>
                  <TableCell sx={styles.cell}>Entry Time (UTC)</TableCell>
                  <TableCell align="right">Entry Price</TableCell>
                  <TableCell sx={styles.cell}>Exit Time (UTC)</TableCell>
                  <TableCell align="right">Exit Price</TableCell>
                  <TableCell align="right">Qty</TableCell>
                  <TableCell align="right">P/L</TableCell>
                  <TableCell>Status</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {roundTrips.map((rt, i) => (
                  <TableRow key={rt.id} hover>
                    <TableCell sx={styles.cell}>{i + 1}</TableCell>
                    <TableCell sx={styles.cell}>
                      {fmtTime(rt.entryTimeMs)}
                    </TableCell>
                    <TableCell align="right" sx={styles.cell}>
                      {rt.entryPrice}
                    </TableCell>
                    <TableCell sx={styles.cell}>
                      {rt.exitTimeMs !== null ? fmtTime(rt.exitTimeMs) : "—"}
                    </TableCell>
                    <TableCell align="right" sx={styles.cell}>
                      {rt.exitPrice ?? "—"}
                    </TableCell>
                    <TableCell align="right" sx={styles.cell}>
                      {rt.qty}
                    </TableCell>
                    <TableCell
                      align="right"
                      sx={{ ...styles.cell, color: plColor(rt.pl) }}
                    >
                      {rt.pl ?? "—"}
                    </TableCell>
                    <TableCell>
                      <Chip
                        label={rt.pl !== null ? "Closed" : "Open"}
                        size="small"
                        color={rt.pl !== null ? "default" : "warning"}
                        sx={{ fontWeight: 600 }}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )}
      </CardContent>
    </Card>
  );
}
