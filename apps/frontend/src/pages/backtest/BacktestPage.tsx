import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import {
  runBacktest,
  runMultiBacktest,
  type BacktestResult,
  type RunMultiBacktestInput,
} from "../../api/backtest";
import BacktestRunForm from "./BacktestRunForm";
import BacktestMetricsCards from "./BacktestMetricsCards";
import BacktestComparisonTable from "./BacktestComparisonTable";
import EquityCurveChart from "./EquityCurveChart";
import BacktestTradeTable from "./BacktestTradeTable";
import AIEvaluationCard from "./AIEvaluationCard";

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
  empty: { color: "text.secondary", textAlign: "center", py: 6 },
  runningInner: {
    display: "flex",
    justifyContent: "center",
    alignItems: "center",
    gap: 2,
    py: 6,
  },
} as const;

export default function BacktestPage() {
  const [results, setResults] = useState<BacktestResult[]>([]);

  const runM = useMutation({
    mutationFn: async (input: RunMultiBacktestInput) => {
      if (input.symbols.length === 1) {
        const res = await runBacktest({
          symbol: input.symbols[0],
          interval: input.interval,
          strategy_name: input.strategy_name,
          strategy_params: input.strategy_params,
          initial_cash: input.initial_cash,
          position_fraction: input.position_fraction,
          stop_loss_pct: input.stop_loss_pct,
          trail_activation_pct: input.trail_activation_pct,
          trail_pct: input.trail_pct,
          from_ms: input.from_ms,
          to_ms: input.to_ms,
          limit: input.limit,
        });
        return [res];
      }
      const multi = await runMultiBacktest(input);
      return multi.results;
    },
    onMutate: () => setResults([]),
    onSuccess: (res) => setResults(res),
  });

  const errMsg =
    runM.error && typeof runM.error === "object" && "message" in runM.error
      ? String((runM.error as { message: unknown }).message)
      : null;

  const isMulti = results.length > 1;

  return (
    <Box sx={styles.root}>
      <Typography variant="h5" sx={{ fontWeight: 600 }}>
        Backtesting
      </Typography>

      <BacktestRunForm
        onSubmit={(input) => runM.mutate(input)}
        pending={runM.isPending}
      />

      {errMsg ? <Alert severity="error">{errMsg}</Alert> : null}

      {runM.isPending ? (
        <Card>
          <CardContent>
            <Box sx={styles.runningInner}>
              <CircularProgress size={20} />
              <Typography sx={{ color: "text.secondary" }}>
                Replaying historical bars…
              </Typography>
            </Box>
          </CardContent>
        </Card>
      ) : null}

      {!runM.isPending && results.length === 0 ? (
        <Card>
          <CardContent>
            <Typography sx={styles.empty}>
              No backtest runs yet. Configure the form above and press{" "}
              <b>Run Backtest</b>.
            </Typography>
          </CardContent>
        </Card>
      ) : null}

      {isMulti ? (
        <Stack spacing={3}>
          <BacktestComparisonTable results={results} />
          {results.map((r) => (
            <Accordion key={r.config.symbol} disableGutters>
              <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                <Typography sx={{ fontWeight: 600, mr: 2 }}>
                  {r.config.symbol}
                </Typography>
                <Typography
                  sx={{
                    color:
                      Number(r.metrics.total_return) >= 0
                        ? "success.main"
                        : "error.main",
                    fontWeight: 600,
                  }}
                >
                  {(Number(r.metrics.total_return) * 100).toFixed(2)}%
                </Typography>
              </AccordionSummary>
              <AccordionDetails>
                <Stack spacing={3}>
                  <BacktestMetricsCards result={r} />
                  <EquityCurveChart points={r.equity_curve} />
                  <BacktestTradeTable trades={r.trades} />
                </Stack>
              </AccordionDetails>
            </Accordion>
          ))}
        </Stack>
      ) : null}

      {!isMulti && results.length === 1 ? (
        <Stack spacing={3}>
          <BacktestMetricsCards result={results[0]} />
          <EquityCurveChart points={results[0].equity_curve} />
          {results[0].config.strategy_name === "ai" ? (
            <AIEvaluationCard backtestId={results[0].id} />
          ) : null}
          <BacktestTradeTable trades={results[0].trades} />
        </Stack>
      ) : null}
    </Box>
  );
}
