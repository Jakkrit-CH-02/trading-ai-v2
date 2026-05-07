import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Stack,
  Typography,
} from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import {
  runBacktest,
  type BacktestResult,
  type RunBacktestInput,
} from "../../api/backtest";
import BacktestRunForm from "./BacktestRunForm";
import BacktestMetricsCards from "./BacktestMetricsCards";
import EquityCurveChart from "./EquityCurveChart";
import BacktestTradeTable from "./BacktestTradeTable";
import AIEvaluationCard from "./AIEvaluationCard";

const styles = {
  root: { p: 3, display: "flex", flexDirection: "column", gap: 3 },
  empty: { color: "text.secondary", textAlign: "center", py: 6 },
  runningInner: { display: "flex", justifyContent: "center", alignItems: "center", gap: 2, py: 6 },
} as const;

export default function BacktestPage() {
  const [result, setResult] = useState<BacktestResult | null>(null);

  const runM = useMutation({
    mutationFn: (input: RunBacktestInput) => runBacktest(input),
    onSuccess: (res) => setResult(res),
  });

  const errMsg =
    runM.error && typeof runM.error === "object" && "message" in runM.error
      ? String((runM.error as { message: unknown }).message)
      : null;

  const isAi = result?.config.strategy_name === "ai";

  return (
    <Box sx={styles.root}>
      <Typography variant="h5" sx={{ fontWeight: 600 }}>
        Backtesting
      </Typography>

      <BacktestRunForm onSubmit={(input) => runM.mutate(input)} pending={runM.isPending} />

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

      {!runM.isPending && !result ? (
        <Card>
          <CardContent>
            <Typography sx={styles.empty}>
              No backtest runs yet. Configure the form above and press <b>Run Backtest</b>.
            </Typography>
          </CardContent>
        </Card>
      ) : null}

      {result ? (
        <Stack spacing={3}>
          <BacktestMetricsCards result={result} />
          <EquityCurveChart points={result.equity_curve} />
          {isAi ? <AIEvaluationCard backtestId={result.id} /> : null}
          <BacktestTradeTable trades={result.trades} />
        </Stack>
      ) : null}
    </Box>
  );
}
