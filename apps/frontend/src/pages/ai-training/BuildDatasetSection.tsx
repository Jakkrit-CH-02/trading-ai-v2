import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  MenuItem,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import {
  buildDataset,
  type BuildDatasetInput,
  type DatasetMetadata,
  type LabelKind,
} from "../../api/ai";

const styles = {
  card: {},
  header: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    mb: 2,
  },
  grid: {
    display: "grid",
    gap: 2,
    gridTemplateColumns: { xs: "1fr", sm: "repeat(2, 1fr)", md: "repeat(3, 1fr)" },
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
} as const;

interface FormValues {
  symbol: string;
  timeframe: string;
  from_ms: number;
  to_ms: number;
  label_kind: LabelKind;
  label_horizon: number;
  label_threshold: number;
  split_train: number;
  split_val: number;
  split_test: number;
}

const DAY_MS = 24 * 60 * 60 * 1000;

const DEFAULTS: FormValues = {
  symbol: "BTCUSDT",
  timeframe: "1h",
  from_ms: Date.now() - 7 * DAY_MS,
  to_ms: Date.now(),
  label_kind: "next_direction",
  label_horizon: 1,
  label_threshold: 0,
  split_train: 0.7,
  split_val: 0.15,
  split_test: 0.15,
};

const LABEL_KINDS: LabelKind[] = [
  "next_direction",
  "future_return",
  "threshold_move",
];

const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d"];

function toBuildInput(v: FormValues): BuildDatasetInput {
  return {
    symbol: v.symbol,
    timeframe: v.timeframe,
    from_ms: Number(v.from_ms),
    to_ms: Number(v.to_ms),
    label: {
      kind: v.label_kind,
      horizon: Number(v.label_horizon),
      threshold: Number(v.label_threshold),
    },
    split: {
      train: Number(v.split_train),
      val: Number(v.split_val),
      test: Number(v.split_test),
    },
  };
}

export default function BuildDatasetSection() {
  const { control, handleSubmit } = useForm<FormValues>({ defaultValues: DEFAULTS });

  const mutation = useMutation<DatasetMetadata, Error, FormValues>({
    mutationFn: (v) => buildDataset(toBuildInput(v)),
  });

  return (
    <Card sx={styles.card}>
      <CardContent>
        <Box sx={styles.header}>
          <Typography variant="h6">Build Dataset</Typography>
        </Box>

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
                <TextField {...field} select label="Timeframe" size="small">
                  {TIMEFRAMES.map((t) => (
                    <MenuItem key={t} value={t}>
                      {t}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <Box />
            <Controller
              name="from_ms"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  type="number"
                  label="From (Unix ms)"
                  size="small"
                />
              )}
            />
            <Controller
              name="to_ms"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  type="number"
                  label="To (Unix ms)"
                  size="small"
                />
              )}
            />
            <Box />
            <Controller
              name="label_kind"
              control={control}
              render={({ field }) => (
                <TextField {...field} select label="Label kind" size="small">
                  {LABEL_KINDS.map((k) => (
                    <MenuItem key={k} value={k}>
                      {k}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <Controller
              name="label_horizon"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  type="number"
                  label="Label horizon (bars)"
                  size="small"
                />
              )}
            />
            <Controller
              name="label_threshold"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  type="number"
                  inputProps={{ step: "0.001" }}
                  label="Label threshold"
                  size="small"
                />
              )}
            />
            <Controller
              name="split_train"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  type="number"
                  inputProps={{ step: "0.05" }}
                  label="Split train"
                  size="small"
                />
              )}
            />
            <Controller
              name="split_val"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  type="number"
                  inputProps={{ step: "0.05" }}
                  label="Split val"
                  size="small"
                />
              )}
            />
            <Controller
              name="split_test"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  type="number"
                  inputProps={{ step: "0.05" }}
                  label="Split test"
                  size="small"
                />
              )}
            />
          </Box>

          <Box>
            <Button
              type="submit"
              variant="contained"
              disabled={mutation.isPending}
            >
              {mutation.isPending ? "Building…" : "Build dataset"}
            </Button>
          </Box>
        </Box>

        {mutation.isError ? (
          <Alert severity="error" sx={styles.result}>
            {mutation.error.message}
          </Alert>
        ) : null}

        {mutation.data ? (
          <Box sx={styles.result}>
            <Alert severity="success" sx={{ mb: 1 }}>
              Dataset built — {mutation.data.rows} rows.
            </Alert>
            <Typography variant="caption" sx={{ color: "text.secondary" }}>
              dataset_id (use this in compute features)
            </Typography>
            <Box sx={styles.pre}>{mutation.data.id}</Box>
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", mt: 1, display: "block" }}
            >
              metadata
            </Typography>
            <Box sx={styles.pre}>{JSON.stringify(mutation.data, null, 2)}</Box>
          </Box>
        ) : null}
      </CardContent>
    </Card>
  );
}
