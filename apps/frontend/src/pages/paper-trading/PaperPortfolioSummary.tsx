import { Box, Card, CardContent, Typography } from "@mui/material";
import type { PaperPortfolio } from "../../api/paper";
import { formatMoney } from "../../lib/format";

export interface PaperPortfolioSummaryProps {
  portfolio: PaperPortfolio;
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: {
      xs: "1fr 1fr",
      md: "repeat(5, 1fr)",
    },
  },
  cell: { display: "flex", flexDirection: "column", gap: 0.5 },
  label: { color: "text.secondary", fontSize: 12, letterSpacing: 0.5 },
  value: { fontSize: 20, fontWeight: 600 },
} as const;

function pnlColor(value: string): "success.main" | "error.main" | "text.primary" {
  const n = Number(value);
  if (!Number.isFinite(n) || n === 0) return "text.primary";
  return n > 0 ? "success.main" : "error.main";
}

export default function PaperPortfolioSummary(props: PaperPortfolioSummaryProps) {
  const { portfolio } = props;
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Portfolio
        </Typography>
        <Box sx={styles.grid}>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>BALANCE (CASH)</Typography>
            <Typography sx={styles.value}>{formatMoney(portfolio.cash)}</Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>EQUITY</Typography>
            <Typography sx={styles.value}>{formatMoney(portfolio.equity)}</Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>REALIZED P&L</Typography>
            <Typography sx={{ ...styles.value, color: pnlColor(portfolio.realized_pl) }}>
              {formatMoney(portfolio.realized_pl)}
            </Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>UNREALIZED P&L</Typography>
            <Typography sx={{ ...styles.value, color: pnlColor(portfolio.unrealized_pl) }}>
              {formatMoney(portfolio.unrealized_pl)}
            </Typography>
          </Box>
          <Box sx={styles.cell}>
            <Typography sx={styles.label}>INITIAL</Typography>
            <Typography sx={styles.value}>
              {formatMoney(portfolio.initial_balance)}
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}
