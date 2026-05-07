import { Box, Card, CardContent, Typography } from "@mui/material";
import type { BacktestMetrics, BacktestResult } from "../../api/backtest";

export interface BacktestMetricsCardsProps {
  result: BacktestResult;
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: {
      xs: "1fr 1fr",
      sm: "repeat(3, 1fr)",
      md: "repeat(6, 1fr)",
    },
  },
  cell: { display: "flex", flexDirection: "column", gap: 0.5 },
  label: { color: "text.secondary", fontSize: 12, letterSpacing: 0.5 },
  value: { fontSize: 18, fontWeight: 600 },
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
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          KPI Summary
        </Typography>
        <Box sx={styles.grid}>
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
          Bars processed: {result.bars_processed} · Initial equity:{" "}
          {result.initial_equity} · Final equity: {result.final_equity}
        </Box>
      </CardContent>
    </Card>
  );
}
