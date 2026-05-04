import {
  Box,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { TradeRecord } from "../../api/trades";
import { formatMoney, formatPrice, formatTime } from "../../lib/format";

export interface TradeTableProps {
  trades: TradeRecord[];
  loading: boolean;
}

const styles = {
  empty: { color: "text.secondary", py: 6, textAlign: "center" },
  reasonCell: {
    maxWidth: 240,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    color: "text.secondary",
  },
} as const;

function pnlColor(value: string): "success.main" | "error.main" | "text.primary" {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text.primary";
  return n > 0 ? "success.main" : "error.main";
}

function modeColor(mode: TradeRecord["mode"]): "warning" | "error" | "info" {
  if (mode === "live") return "error";
  if (mode === "paper") return "warning";
  return "info";
}

function aiConfidence(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "—";
  return `${(n * 100).toFixed(1)}%`;
}

export default function TradeTable(props: TradeTableProps) {
  const { trades, loading } = props;

  if (loading && trades.length === 0) {
    return (
      <Box sx={styles.empty}>
        <Typography>Loading trades…</Typography>
      </Box>
    );
  }

  if (trades.length === 0) {
    return (
      <Box sx={styles.empty}>
        <Typography>No trades match the current filters.</Typography>
      </Box>
    );
  }

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Time</TableCell>
          <TableCell>Mode</TableCell>
          <TableCell>Symbol</TableCell>
          <TableCell>Strategy</TableCell>
          <TableCell>Side</TableCell>
          <TableCell align="right">Qty</TableCell>
          <TableCell align="right">Fill Price</TableCell>
          <TableCell align="right">Fee</TableCell>
          <TableCell align="right">Realized P&L</TableCell>
          <TableCell align="right">AI Conf</TableCell>
          <TableCell>Reason</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {trades.map((t) => (
          <TableRow key={t.id} hover>
            <TableCell sx={{ color: "text.secondary" }}>
              {formatTime(t.timestamp_ms)}
            </TableCell>
            <TableCell>
              <Chip
                label={t.mode.toUpperCase()}
                size="small"
                color={modeColor(t.mode)}
                sx={{ fontWeight: 600 }}
              />
            </TableCell>
            <TableCell sx={{ fontWeight: 600 }}>{t.symbol}</TableCell>
            <TableCell>{t.strategy || "—"}</TableCell>
            <TableCell>
              <Chip
                label={t.side.toUpperCase()}
                size="small"
                color={t.side === "buy" ? "success" : "error"}
                sx={{ fontWeight: 600 }}
              />
            </TableCell>
            <TableCell align="right">{formatPrice(t.qty)}</TableCell>
            <TableCell align="right">{formatPrice(t.fill_price)}</TableCell>
            <TableCell align="right">{formatMoney(t.fee)}</TableCell>
            <TableCell align="right" sx={{ color: pnlColor(t.realized_pl) }}>
              {formatMoney(t.realized_pl)}
            </TableCell>
            <TableCell align="right">{aiConfidence(t.ai_confidence)}</TableCell>
            <TableCell sx={styles.reasonCell} title={t.reason}>
              {t.reason || "—"}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
