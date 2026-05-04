import {
  Box,
  Card,
  CardContent,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import type { RiskSnapshot } from "../../api/risk";

export interface RiskLimitProgressProps {
  snap: RiskSnapshot;
}

function pct(s: string): number {
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

function fmtPct(s: string, dp = 2): string {
  return `${(pct(s) * 100).toFixed(dp)}%`;
}

const styles = {
  card: { mt: 0 },
  bps: { fontFamily: "monospace" },
} as const;

export default function RiskLimitProgress(props: RiskLimitProgressProps) {
  const { snap } = props;
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Limits & Slippage
        </Typography>
        <Box sx={styles.card}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Metric</TableCell>
                <TableCell align="right">Current</TableCell>
                <TableCell align="right">Limit</TableCell>
                <TableCell align="right">Headroom</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>Risk per trade (largest position)</TableCell>
                <TableCell align="right">
                  {fmtPct(snap.largest_position_pct)}
                </TableCell>
                <TableCell align="right">
                  {fmtPct(snap.max_position_pct)}
                </TableCell>
                <TableCell align="right">
                  {fmtPct(
                    String(
                      Math.max(
                        0,
                        pct(snap.max_position_pct) -
                          pct(snap.largest_position_pct),
                      ),
                    ),
                  )}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Daily drawdown</TableCell>
                <TableCell align="right">
                  {fmtPct(snap.daily_drawdown_pct)}
                </TableCell>
                <TableCell align="right">
                  {fmtPct(snap.max_daily_drawdown_pct)}
                </TableCell>
                <TableCell align="right">
                  {fmtPct(
                    String(
                      Math.max(
                        0,
                        pct(snap.max_daily_drawdown_pct) -
                          pct(snap.daily_drawdown_pct),
                      ),
                    ),
                  )}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Max slippage (market orders)</TableCell>
                <TableCell align="right" sx={styles.bps}>
                  —
                </TableCell>
                <TableCell align="right" sx={styles.bps}>
                  {snap.max_slippage_bps} bps
                </TableCell>
                <TableCell align="right" sx={styles.bps}>
                  {snap.max_slippage_bps} bps
                </TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Box>
      </CardContent>
    </Card>
  );
}
