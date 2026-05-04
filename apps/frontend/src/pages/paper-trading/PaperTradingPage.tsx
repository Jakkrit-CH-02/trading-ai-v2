import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import RestartAltIcon from "@mui/icons-material/RestartAlt";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import {
  getPaperPortfolio,
  getPaperTrades,
  resetPaperPortfolio,
  type PaperPortfolio,
} from "../../api/paper";
import PaperPortfolioSummary from "./PaperPortfolioSummary";
import PaperPositionTable from "./PaperPositionTable";
import PaperTradeHistory from "./PaperTradeHistory";
import EquityCurve from "./EquityCurve";
import ResetPaperPortfolioDialog from "./ResetPaperPortfolioDialog";

const POLL_MS = 2000;

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
  banner: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 2,
    p: 2,
    borderRadius: 1,
    bgcolor: "warning.dark",
    color: "warning.contrastText",
    flexWrap: "wrap",
  },
  bannerLeft: { display: "flex", alignItems: "center", gap: 2 },
  perfGrid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(5, 1fr)" },
  },
  perfCell: { display: "flex", flexDirection: "column", gap: 0.5 },
  perfLabel: { color: "text.secondary", fontSize: 12, letterSpacing: 0.5 },
  perfValue: { fontSize: 18, fontWeight: 600 },
} as const;

function PerformanceCard({ portfolio }: { portfolio: PaperPortfolio }) {
  const perf = portfolio.performance;
  return (
    <Card>
      <CardContent>
        <Typography variant="subtitle1" sx={{ fontWeight: 600, mb: 2 }}>
          Performance Summary
        </Typography>
        <Box sx={styles.perfGrid}>
          <Box sx={styles.perfCell}>
            <Typography sx={styles.perfLabel}>TRADES</Typography>
            <Typography sx={styles.perfValue}>{perf.total_trades}</Typography>
          </Box>
          <Box sx={styles.perfCell}>
            <Typography sx={styles.perfLabel}>WINS</Typography>
            <Typography sx={{ ...styles.perfValue, color: "success.main" }}>
              {perf.win_trades}
            </Typography>
          </Box>
          <Box sx={styles.perfCell}>
            <Typography sx={styles.perfLabel}>LOSSES</Typography>
            <Typography sx={{ ...styles.perfValue, color: "error.main" }}>
              {perf.loss_trades}
            </Typography>
          </Box>
          <Box sx={styles.perfCell}>
            <Typography sx={styles.perfLabel}>WIN RATE</Typography>
            <Typography sx={styles.perfValue}>
              {perf.total_trades === 0
                ? "—"
                : `${(perf.win_rate * 100).toFixed(1)}%`}
            </Typography>
          </Box>
          <Box sx={styles.perfCell}>
            <Typography sx={styles.perfLabel}>TOTAL REALIZED</Typography>
            <Typography
              sx={{
                ...styles.perfValue,
                color:
                  Number(perf.total_realized_pl) > 0
                    ? "success.main"
                    : Number(perf.total_realized_pl) < 0
                      ? "error.main"
                      : "text.primary",
              }}
            >
              {perf.total_realized_pl}
            </Typography>
          </Box>
        </Box>
      </CardContent>
    </Card>
  );
}

export default function PaperTradingPage() {
  const qc = useQueryClient();
  const [resetOpen, setResetOpen] = useState(false);
  const [errMsg, setErrMsg] = useState<string | null>(null);

  const portfolioQ = useQuery({
    queryKey: ["paper", "portfolio"],
    queryFn: getPaperPortfolio,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
  });

  const tradesQ = useQuery({
    queryKey: ["paper", "trades"],
    queryFn: getPaperTrades,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
  });

  const resetM = useMutation({
    mutationFn: resetPaperPortfolio,
    onSuccess: (data) => {
      qc.setQueryData(["paper", "portfolio"], data);
      qc.invalidateQueries({ queryKey: ["paper", "trades"] });
      setResetOpen(false);
      setErrMsg(null);
    },
    onError: (err: unknown) => {
      const m =
        err && typeof err === "object" && "message" in err
          ? String((err as { message: unknown }).message)
          : "Failed to reset paper portfolio";
      setErrMsg(m);
    },
  });

  const portfolio = portfolioQ.data;

  return (
    <Box sx={styles.root}>
      <Box sx={styles.banner}>
        <Box sx={styles.bannerLeft}>
          <Chip
            label="PAPER TRADING"
            color="warning"
            sx={{ fontWeight: 700, letterSpacing: 1 }}
          />
          <Typography sx={{ fontSize: 14 }}>
            Simulated portfolio — no real orders are sent to Binance.
          </Typography>
        </Box>
        <Button
          variant="outlined"
          color="inherit"
          size="small"
          startIcon={<RestartAltIcon />}
          onClick={() => setResetOpen(true)}
          disabled={!portfolio || resetM.isPending}
        >
          Reset Portfolio
        </Button>
      </Box>

      {errMsg ? <Alert severity="error">{errMsg}</Alert> : null}

      {portfolioQ.isLoading || !portfolio ? (
        <Card>
          <CardContent
            sx={{ display: "flex", justifyContent: "center", py: 6 }}
          >
            {portfolioQ.isError ? (
              <Typography color="error">
                Could not fetch /api/paper/portfolio.
              </Typography>
            ) : (
              <CircularProgress size={24} />
            )}
          </CardContent>
        </Card>
      ) : (
        <Stack spacing={3}>
          <PaperPortfolioSummary portfolio={portfolio} />
          <EquityCurve points={portfolio.equity_curve} />
          <PaperPositionTable positions={portfolio.positions} />
          <PerformanceCard portfolio={portfolio} />
          <PaperTradeHistory trades={tradesQ.data?.trades ?? []} />
        </Stack>
      )}

      <ResetPaperPortfolioDialog
        open={resetOpen}
        pending={resetM.isPending}
        onCancel={() => setResetOpen(false)}
        onConfirm={() => resetM.mutate()}
      />
    </Box>
  );
}
