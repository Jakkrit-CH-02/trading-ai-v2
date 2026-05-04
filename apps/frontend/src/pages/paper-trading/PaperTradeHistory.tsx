import {
  Card,
  CardContent,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { PaperTrade } from "../../api/paper";
import { formatMoney, formatPrice, formatTime } from "../../lib/format";

export interface PaperTradeHistoryProps {
  trades: PaperTrade[];
  limit?: number;
}

const styles = {
  empty: { color: "text.secondary", py: 3, textAlign: "center" },
} as const;

function pnlColor(value: string): "success.main" | "error.main" | "text.primary" {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text.primary";
  return n > 0 ? "success.main" : "error.main";
}

export default function PaperTradeHistory(props: PaperTradeHistoryProps) {
  const { trades, limit = 25 } = props;
  const recent = [...trades]
    .sort((a, b) => b.timestamp_ms - a.timestamp_ms)
    .slice(0, limit);
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
          Recent Fills
        </Typography>
        {recent.length === 0 ? (
          <Typography sx={styles.empty}>No fills yet.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Time</TableCell>
                <TableCell>Symbol</TableCell>
                <TableCell>Side</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Fill Price</TableCell>
                <TableCell align="right">Realized P&L</TableCell>
                <TableCell align="right">Cash</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {recent.map((t) => (
                <TableRow key={t.order_id}>
                  <TableCell sx={{ color: "text.secondary" }}>
                    {formatTime(t.timestamp_ms)}
                  </TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>{t.symbol}</TableCell>
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
                  <TableCell align="right" sx={{ color: pnlColor(t.realized_pl) }}>
                    {formatMoney(t.realized_pl)}
                  </TableCell>
                  <TableCell align="right">{formatMoney(t.cash)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
