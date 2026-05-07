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

const styles = {
  empty: { color: "text.secondary", textAlign: "center", py: 4 },
  cell: { whiteSpace: "nowrap" },
} as const;

function fmtTime(ms: number): string {
  return new Date(ms).toISOString().slice(0, 19).replace("T", " ");
}

function plColor(s: string): string {
  const n = Number(s);
  if (!Number.isFinite(n) || n === 0) return "text.primary";
  return n > 0 ? "success.main" : "error.main";
}

export default function BacktestTradeTable(props: BacktestTradeTableProps) {
  const { trades } = props;
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Trades ({trades.length})
        </Typography>
        {trades.length === 0 ? (
          <Typography sx={styles.empty}>No trades produced.</Typography>
        ) : (
          <TableContainer sx={{ maxHeight: 480 }}>
            <Table size="small" stickyHeader>
              <TableHead>
                <TableRow>
                  <TableCell sx={styles.cell}>Time (UTC)</TableCell>
                  <TableCell>Side</TableCell>
                  <TableCell align="right">Qty</TableCell>
                  <TableCell align="right">Price</TableCell>
                  <TableCell align="right">Realized P/L</TableCell>
                  <TableCell>Reason</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {trades.map((t) => (
                  <TableRow key={t.order_id} hover>
                    <TableCell sx={styles.cell}>{fmtTime(t.timestamp_ms)}</TableCell>
                    <TableCell>
                      <Chip
                        label={t.side}
                        size="small"
                        color={t.side.toUpperCase() === "BUY" ? "success" : "error"}
                        sx={{ fontWeight: 600 }}
                      />
                    </TableCell>
                    <TableCell align="right" sx={styles.cell}>
                      {t.qty}
                    </TableCell>
                    <TableCell align="right" sx={styles.cell}>
                      {t.price}
                    </TableCell>
                    <TableCell align="right" sx={{ ...styles.cell, color: plColor(t.realized_pl) }}>
                      {t.realized_pl}
                    </TableCell>
                    <TableCell sx={{ color: "text.secondary" }}>{t.reason}</TableCell>
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
