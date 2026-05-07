import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  CircularProgress,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import PsychologyIcon from "@mui/icons-material/Psychology";
import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { runEvaluation, type EvaluationReport } from "../../api/backtest";

export interface AIEvaluationCardProps {
  backtestId: string;
}

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr 1fr", md: "repeat(4, 1fr)" },
  },
  cell: { display: "flex", flexDirection: "column", gap: 0.5 },
  label: { color: "text.secondary", fontSize: 12, letterSpacing: 0.5 },
  value: { fontSize: 18, fontWeight: 600 },
} as const;

export default function AIEvaluationCard(props: AIEvaluationCardProps) {
  const { backtestId } = props;
  const [modelId, setModelId] = useState("");
  const [report, setReport] = useState<EvaluationReport | null>(null);

  const evalM = useMutation({
    mutationFn: () => runEvaluation({ backtest_id: backtestId, model_id: modelId.trim() }),
    onSuccess: (r) => setReport(r),
  });

  const errMsg =
    evalM.error && typeof evalM.error === "object" && "message" in evalM.error
      ? String((evalM.error as { message: unknown }).message)
      : null;

  return (
    <Card>
      <CardContent>
        <Stack
          direction={{ xs: "column", sm: "row" }}
          spacing={2}
          alignItems={{ sm: "center" }}
          sx={{ mb: 2 }}
        >
          <Typography variant="subtitle1" sx={{ fontWeight: 600, flex: 1 }}>
            AI Evaluation
          </Typography>
          <TextField
            label="Model ID"
            size="small"
            value={modelId}
            onChange={(e) => setModelId(e.target.value)}
            sx={{ minWidth: 240 }}
          />
          <Button
            variant="contained"
            color="secondary"
            startIcon={
              evalM.isPending ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <PsychologyIcon />
              )
            }
            onClick={() => evalM.mutate()}
            disabled={!modelId.trim() || evalM.isPending}
          >
            Evaluate AI
          </Button>
        </Stack>

        {errMsg ? (
          <Alert severity="error" sx={{ mb: 2 }}>
            {errMsg}
          </Alert>
        ) : null}

        {report ? (
          <Box>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
              <Chip
                label={report.passed ? "PASSED" : "FAILED"}
                color={report.passed ? "success" : "error"}
                sx={{ fontWeight: 700 }}
              />
              <Typography sx={{ color: "text.secondary", fontSize: 13 }}>
                {report.reason}
              </Typography>
            </Stack>
            <Box sx={styles.grid}>
              <Box sx={styles.cell}>
                <Typography sx={styles.label}>PRECISION</Typography>
                <Typography sx={styles.value}>
                  {(report.metrics.precision * 100).toFixed(2)}%
                </Typography>
              </Box>
              <Box sx={styles.cell}>
                <Typography sx={styles.label}>RECALL</Typography>
                <Typography sx={styles.value}>
                  {(report.metrics.recall * 100).toFixed(2)}%
                </Typography>
              </Box>
              <Box sx={styles.cell}>
                <Typography sx={styles.label}>CALIBRATION ERR</Typography>
                <Typography sx={styles.value}>
                  {report.metrics.calibration_error.toFixed(4)}
                </Typography>
              </Box>
              <Box sx={styles.cell}>
                <Typography sx={styles.label}>FEATURE DRIFT</Typography>
                <Typography sx={styles.value}>
                  {report.metrics.feature_drift.toFixed(4)}
                </Typography>
              </Box>
            </Box>
            <Typography sx={{ mt: 2, color: "text.secondary", fontSize: 12 }}>
              Eval ID: {report.id} · Model: {report.model_id} · Backtest: {report.backtest_id}
            </Typography>
          </Box>
        ) : (
          <Typography sx={{ color: "text.secondary", fontSize: 13 }}>
            Provide a model ID and run evaluation to grade the AI strategy on this backtest.
          </Typography>
        )}
      </CardContent>
    </Card>
  );
}
