import { Alert, Box, Card, CardContent, Typography } from "@mui/material";
import type { BacktestMetrics, BacktestResult } from "../../api/backtest";
import { formatTime } from "../../lib/format";

export interface BacktestMetricsCardsProps {
  result: BacktestResult;
}

export function netProfitAbs(initialEquity: string, finalEquity: string): number {
  return Number(finalEquity) - Number(initialEquity);
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: {
      xs: "1fr 1fr",
      sm: "repeat(3, 1fr)",
      md: "repeat(4, 1fr)",
      lg: "repeat(7, 1fr)",
    },
  },
  cell: { display: "flex", flexDirection: "column", gap: 0.5 },
  label: { color: "text.secondary", fontSize: 12, letterSpacing: 0.5 },
  value: { fontSize: 18, fontWeight: 600 },
  heroValue: { fontSize: 22, fontWeight: 600 },
  subLine: { fontSize: 11, color: "text.secondary" },
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
  const requestedFrom = result.config.from_ms;
  const requestedTo = result.config.to_ms;
  const actualFrom = result.start_ms;
  const actualTo = result.end_ms;
  const fromClamped = requestedFrom != null && requestedFrom < actualFrom;
  const toClamped = requestedTo != null && requestedTo > actualTo;
  const showRangeWarning = fromClamped || toClamped;

  const np = netProfitAbs(result.initial_equity, result.final_equity);
  const npColor =
    np > 0 ? "success.main" : np < 0 ? "error.main" : "text.primary";
  const retPct = Number(m.total_return);

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          KPI Summary
        </Typography>
        <Box sx={styles.grid}>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>NET PROFIT</Typography>
            <Typography sx={{ ...styles.heroValue, color: npColor }}>
              {`${np > 0 ? "+" : ""}${np.toFixed(2)}`}
            </Typography>
            <Typography sx={styles.subLine}>
              ${result.initial_equity} → ${result.final_equity}
            </Typography>
            <Typography sx={styles.subLine}>
              {Number.isFinite(retPct)
                ? `${retPct >= 0 ? "+" : ""}${(retPct * 100).toFixed(2)}%`
                : "—"}
            </Typography>
          </Box>
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
          Bars processed: {result.bars_processed}
        </Box>
        <Box sx={{ mt: 2, display: "flex", flexDirection: "column", gap: 0.75 }}>
          <Typography sx={{ color: "text.secondary", fontSize: 12 }}>
            Requested range:{" "}
            {requestedFrom != null || requestedTo != null
              ? `${requestedFrom != null ? formatTime(requestedFrom) : "Earliest available"} to ${requestedTo != null ? formatTime(requestedTo) : "Latest available"}`
              : "Latest available bars"}
          </Typography>
          <Typography sx={{ color: "text.secondary", fontSize: 12 }}>
            Actual range used: {formatTime(actualFrom)} to {formatTime(actualTo)}
          </Typography>
        </Box>
        {showRangeWarning ? (
          <Alert severity="info" sx={{ mt: 2 }}>
            Historical data was only available for part of the requested window, so the
            backtest started from the earliest available bar in that range.
          </Alert>
        ) : null}
      </CardContent>
    </Card>
  );
}
