import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import {
  predict,
  type PredictInput,
  type PredictResponse,
} from "../../api/ai";

const styles = {
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)" },
  },
  result: { mt: 2 },
  pre: {
    fontFamily: "monospace",
    fontSize: 12,
    whiteSpace: "pre-wrap",
    bgcolor: "background.default",
    p: 1.5,
    borderRadius: 1,
    overflowX: "auto",
  },
  panel: {
    mt: 2,
    p: 2,
    border: 1,
    borderColor: "divider",
    borderRadius: 1,
    bgcolor: "background.default",
  },
  chips: { display: "flex", gap: 1, flexWrap: "wrap", mt: 1 },
} as const;

interface FormValues {
  symbol: string;
  timeframe: string;
  features_json: string;
}

function parseFeatures(raw: string): Record<string, number> {
  const trimmed = raw.trim();
  if (!trimmed) return {};
  const parsed = JSON.parse(trimmed) as unknown;
  if (
    typeof parsed !== "object" ||
    parsed === null ||
    Array.isArray(parsed)
  ) {
    throw new Error("features must be a JSON object of name -> number");
  }
  const out: Record<string, number> = {};
  for (const [k, v] of Object.entries(parsed)) {
    const n = Number(v);
    if (!Number.isFinite(n)) {
      throw new Error(`feature "${k}" must be a number`);
    }
    out[k] = n;
  }
  return out;
}

const SAMPLE_FEATURES = `{
  "rsi_14": 55.2,
  "ema_20": 30150.0,
  "ema_50": 29900.5,
  "ret_1": 0.0021,
  "vol_zscore_20": 0.4
}`;

function signalColor(s: PredictResponse["signal"]): "success" | "error" | "default" {
  if (s === "BUY") return "success";
  if (s === "SELL") return "error";
  return "default";
}

export default function PredictExplainSection() {
  const { control, handleSubmit } = useForm<FormValues>({
    defaultValues: {
      symbol: "BTCUSDT",
      timeframe: "1h",
      features_json: SAMPLE_FEATURES,
    },
  });

  const mutation = useMutation<PredictResponse, Error, FormValues>({
    mutationFn: (v) => {
      const features = parseFeatures(v.features_json);
      const input: PredictInput = {
        symbol: v.symbol.trim(),
        timeframe: v.timeframe.trim(),
        features,
      };
      return predict(input, true);
    },
  });

  const r = mutation.data;
  const ex = r?.explanation ?? null;

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Sample Prediction
        </Typography>

        <Box
          component="form"
          onSubmit={handleSubmit((v) => mutation.mutate(v))}
          sx={{ display: "flex", flexDirection: "column", gap: 2 }}
        >
          <Box sx={styles.grid}>
            <Controller
              name="symbol"
              control={control}
              render={({ field }) => (
                <TextField {...field} label="Symbol" size="small" />
              )}
            />
            <Controller
              name="timeframe"
              control={control}
              render={({ field }) => (
                <TextField {...field} label="Timeframe" size="small" />
              )}
            />
          </Box>
          <Controller
            name="features_json"
            control={control}
            render={({ field }) => (
              <TextField
                {...field}
                label="Features (JSON)"
                multiline
                minRows={6}
                size="small"
                sx={{ fontFamily: "monospace" }}
              />
            )}
          />
          <Box>
            <Button
              type="submit"
              variant="contained"
              disabled={mutation.isPending}
            >
              {mutation.isPending ? "Predicting…" : "Run prediction"}
            </Button>
          </Box>
        </Box>

        {mutation.isError ? (
          <Alert severity="error" sx={styles.result}>
            {mutation.error.message}
          </Alert>
        ) : null}

        {r ? (
          <Box sx={styles.result}>
            <Stack direction="row" spacing={1} alignItems="center">
              <Chip
                label={r.signal}
                color={signalColor(r.signal)}
                size="small"
              />
              <Typography variant="body2">
                confidence {r.confidence.toFixed(3)} · risk{" "}
                {r.risk_score.toFixed(3)}
              </Typography>
              {r.cached ? <Chip size="small" label="cached" /> : null}
            </Stack>
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", display: "block", mt: 1 }}
            >
              {r.reason}
            </Typography>

            {ex ? (
              <Box sx={styles.panel}>
                <Typography variant="subtitle2">Explanation</Typography>
                <Typography variant="body2" sx={{ mt: 0.5 }}>
                  {ex.reason}
                </Typography>
                <Typography variant="caption" sx={{ color: "text.secondary" }}>
                  {ex.confidence_explanation}
                </Typography>

                <Box sx={styles.chips}>
                  {ex.top_features.map((f) => (
                    <Chip key={f} size="small" label={f} />
                  ))}
                </Box>

                <Table size="small" sx={{ mt: 1 }}>
                  <TableHead>
                    <TableRow>
                      <TableCell>Feature</TableCell>
                      <TableCell align="right">Value</TableCell>
                      <TableCell align="right">Importance</TableCell>
                      <TableCell align="right">Contribution</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {ex.contributions.map((c) => (
                      <TableRow key={c.name}>
                        <TableCell sx={{ fontFamily: "monospace", fontSize: 12 }}>
                          {c.name}
                        </TableCell>
                        <TableCell align="right">{c.value.toFixed(4)}</TableCell>
                        <TableCell align="right">
                          {c.importance.toFixed(4)}
                        </TableCell>
                        <TableCell align="right">
                          {c.contribution.toFixed(4)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            ) : null}

            <Typography
              variant="caption"
              sx={{ color: "text.secondary", mt: 1, display: "block" }}
            >
              raw response
            </Typography>
            <Box sx={styles.pre}>{JSON.stringify(r, null, 2)}</Box>
          </Box>
        ) : null}
      </CardContent>
    </Card>
  );
}
