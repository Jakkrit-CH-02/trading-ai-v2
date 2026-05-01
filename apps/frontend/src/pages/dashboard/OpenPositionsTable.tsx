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
import type { Position } from "../../api/dashboard";

export interface OpenPositionsTableProps {
  positions: Position[];
}

const styles = {
  empty: {
    p: 6,
    display: "flex",
    flexDirection: "column",
    alignItems: "center",
    gap: 1,
  },
  num: { fontVariantNumeric: "tabular-nums" },
  pnl: (n: number) => ({
    fontVariantNumeric: "tabular-nums",
    color: n > 0 ? "success.main" : n < 0 ? "error.main" : "text.secondary",
  }),
} as const;

function formatSignedNumber(value: string): string {
  const n = Number(value);
  if (!Number.isFinite(n)) return value;
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(2)}`;
}

export default function OpenPositionsTable(props: OpenPositionsTableProps) {
  const { positions } = props;

  if (positions.length === 0) {
    return (
      <Box sx={styles.empty}>
        <Typography sx={{ color: "text.secondary" }}>
          No open positions.
        </Typography>
        <Typography variant="caption" sx={{ color: "text.disabled" }}>
          Positions opened by the bot will appear here.
        </Typography>
      </Box>
    );
  }

  return (
    <Table size="small">
      <TableHead>
        <TableRow>
          <TableCell>Symbol</TableCell>
          <TableCell>Side</TableCell>
          <TableCell align="right">Qty</TableCell>
          <TableCell align="right">Entry</TableCell>
          <TableCell align="right">Mark</TableCell>
          <TableCell align="right">Unrealized PnL</TableCell>
        </TableRow>
      </TableHead>
      <TableBody>
        {positions.map((p) => {
          const pnlNum = Number(p.unrealized_pnl);
          return (
            <TableRow key={p.id} hover>
              <TableCell sx={{ fontWeight: 600 }}>{p.symbol}</TableCell>
              <TableCell>
                <Chip
                  size="small"
                  label={p.side.toUpperCase()}
                  color={p.side === "long" ? "success" : "error"}
                  variant="outlined"
                />
              </TableCell>
              <TableCell align="right" sx={styles.num}>
                {p.qty}
              </TableCell>
              <TableCell align="right" sx={styles.num}>
                {p.entry_price}
              </TableCell>
              <TableCell align="right" sx={styles.num}>
                {p.mark_price}
              </TableCell>
              <TableCell align="right" sx={styles.pnl(pnlNum)}>
                {formatSignedNumber(p.unrealized_pnl)}
              </TableCell>
            </TableRow>
          );
        })}
      </TableBody>
    </Table>
  );
}
