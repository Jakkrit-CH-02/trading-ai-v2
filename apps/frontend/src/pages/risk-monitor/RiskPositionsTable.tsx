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
import type { RiskPosition } from "../../api/risk";

export interface RiskPositionsTableProps {
  positions: RiskPosition[];
}

function fmtPct(s: string, dp = 2): string {
  const n = Number(s);
  return Number.isFinite(n) ? `${(n * 100).toFixed(dp)}%` : s;
}

export default function RiskPositionsTable(props: RiskPositionsTableProps) {
  const { positions } = props;
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Open Positions
        </Typography>
        {positions.length === 0 ? (
          <Typography sx={{ color: "text.secondary" }}>
            No open positions.
          </Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Symbol</TableCell>
                <TableCell align="right">Qty</TableCell>
                <TableCell align="right">Avg Entry</TableCell>
                <TableCell align="right">% of Equity</TableCell>
                <TableCell align="right">Unrealized</TableCell>
                <TableCell align="right">Realized</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {positions.map((p) => (
                <TableRow key={p.symbol}>
                  <TableCell>{p.symbol}</TableCell>
                  <TableCell align="right">{p.qty}</TableCell>
                  <TableCell align="right">{p.avg_entry}</TableCell>
                  <TableCell align="right">
                    {fmtPct(p.notional_pct)}
                  </TableCell>
                  <TableCell
                    align="right"
                    sx={{
                      color:
                        Number(p.unrealized_pl) > 0
                          ? "success.main"
                          : Number(p.unrealized_pl) < 0
                            ? "error.main"
                            : "text.primary",
                    }}
                  >
                    {p.unrealized_pl}
                  </TableCell>
                  <TableCell align="right">{p.realized_pl}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
