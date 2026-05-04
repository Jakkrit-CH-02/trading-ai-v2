import {
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { PaperPosition } from "../../api/paper";
import { formatMoney, formatPrice, formatTime } from "../../lib/format";

export interface PaperPositionTableProps {
  positions: PaperPosition[];
}

const styles = {
  empty: { color: "text.secondary", py: 3, textAlign: "center" },
} as const;

function pnlColor(value: string): "success.main" | "error.main" | "text.primary" {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text.primary";
  return n > 0 ? "success.main" : "error.main";
}

export default function PaperPositionTable(props: PaperPositionTableProps) {
  const { positions } = props;
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 1 }}>
          Open Positions
        </Typography>
        {positions.length === 0 ? (
          <Typography sx={styles.empty}>No open positions.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Avg Entry</TableCell>
                <TableCell align="right">Unrealized P&L</TableCell>
                <TableCell align="right">Realized P&L</TableCell>
                <TableCell align="right">Updated</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {positions.map((p) => (
                <TableRow key={p.symbol}>
                  <TableCell sx={{ fontWeight: 600 }}>{p.symbol}</TableCell>
                  <TableCell align="right">{formatPrice(p.qty)}</TableCell>
                  <TableCell align="right">{formatPrice(p.avg_entry)}</TableCell>
                  <TableCell align="right" sx={{ color: pnlColor(p.unrealized_pl) }}>
                    {formatMoney(p.unrealized_pl)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: pnlColor(p.realized_pl) }}>
                    {formatMoney(p.realized_pl)}
                  </TableCell>
                  <TableCell align="right" sx={{ color: "text.secondary" }}>
                    {formatTime(p.updated_ms)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
