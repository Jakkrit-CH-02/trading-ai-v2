import { Box, Card, CardContent, LinearProgress, Typography } from "@mui/material";
import type { RiskSnapshot } from "../../api/risk";

export interface RiskSummaryCardsProps {
  snap: RiskSnapshot;
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" },
  },
  cell: { display: "flex", flexDirection: "column", gap: 0.5 },
  label: { color: "text.secondary", fontSize: 12, letterSpacing: 0.5 },
  value: { fontSize: 20, fontWeight: 600 },
  sub: { color: "text.secondary", fontSize: 12 },
} as const;

function pct(s: string): number {
  const n = Number(s);
  return Number.isFinite(n) ? n : 0;
}

function fmtPct(s: string, dp = 2): string {
  return `${(pct(s) * 100).toFixed(dp)}%`;
}

function fmtMoney(s: string): string {
  const n = Number(s);
  if (!Number.isFinite(n)) return s;
  return n.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function severity(ratio: number): "ok" | "warn" | "crit" {
  if (ratio >= 1) return "crit";
  if (ratio >= 0.75) return "warn";
  return "ok";
}

function sevColor(s: "ok" | "warn" | "crit") {
  if (s === "crit") return "error.main";
  if (s === "warn") return "warning.main";
  return "success.main";
}

export default function RiskSummaryCards(props: RiskSummaryCardsProps) {
  const { snap } = props;
  const exposureRatio = pct(snap.exposure_pct);
  const drawdownRatio =
    pct(snap.max_daily_drawdown_pct) > 0
      ? pct(snap.daily_drawdown_pct) / pct(snap.max_daily_drawdown_pct)
      : 0;
  const largestRatio =
    pct(snap.max_position_pct) > 0
      ? pct(snap.largest_position_pct) / pct(snap.max_position_pct)
      : 0;
  const ddSev = severity(drawdownRatio);
  const posSev = severity(largestRatio);

  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Risk Summary
        </Typography>
        <Box sx={styles.grid}>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>EQUITY</Typography>
            <Typography sx={styles.value}>{fmtMoney(snap.equity)}</Typography>
            <Typography sx={styles.sub}>
              cash {fmtMoney(snap.cash)} · initial {fmtMoney(snap.initial_equity)}
            </Typography>
          </Box>

          <Box sx={styles.cell}>
            <Typography sx={styles.label}>EXPOSURE</Typography>
            <Typography sx={styles.value}>{fmtMoney(snap.exposure)}</Typography>
            <Typography sx={styles.sub}>{fmtPct(snap.exposure_pct)} of equity</Typography>
            <LinearProgress
              variant="determinate"
              value={Math.min(100, Math.max(0, exposureRatio * 100))}
              sx={{ mt: 0.5, height: 6, borderRadius: 1 }}
            />
          </Box>

          <Box sx={styles.cell}>
            <Typography sx={styles.label}>DAILY P&L</Typography>
            <Typography
              sx={{
                ...styles.value,
                color:
                  Number(snap.daily_pnl) > 0
                    ? "success.main"
                    : Number(snap.daily_pnl) < 0
                      ? "error.main"
                      : "text.primary",
              }}
            >
              {fmtMoney(snap.daily_pnl)}
            </Typography>
            <Typography sx={styles.sub}>
              drawdown {fmtPct(snap.daily_drawdown_pct)} / limit{" "}
              {fmtPct(snap.max_daily_drawdown_pct)}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={Math.min(100, Math.max(0, drawdownRatio * 100))}
              sx={{
                mt: 0.5,
                height: 6,
                borderRadius: 1,
                "& .MuiLinearProgress-bar": { bgcolor: sevColor(ddSev) },
              }}
            />
          </Box>

          <Box sx={styles.cell}>
            <Typography sx={styles.label}>OPEN POSITIONS</Typography>
            <Typography sx={styles.value}>{snap.open_positions}</Typography>
            <Typography sx={styles.sub}>
              largest {fmtPct(snap.largest_position_pct)} / limit{" "}
              {fmtPct(snap.max_position_pct)}
            </Typography>
            <LinearProgress
              variant="determinate"
              value={Math.min(100, Math.max(0, largestRatio * 100))}
              sx={{
                mt: 0.5,
                height: 6,
                borderRadius: 1,
                "& .MuiLinearProgress-bar": { bgcolor: sevColor(posSev) },
              }}
            />
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}
