import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  MenuItem,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import {
  runTraining,
  type ModelKind,
  type RunTrainingInput,
  type TrainingJob,
} from "../../api/ai";

const styles = {
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
  chips: { display: "flex", gap: 1, flexWrap: "wrap", mb: 1 },
  metricRow: {
    display: "grid",
    gap: 1,
    gridTemplateColumns: { xs: "1fr 1fr", sm: "repeat(4, 1fr)" },
    mt: 1,
  },
  metricCell: {
    p: 1,
    bgcolor: "background.default",
    borderRadius: 1,
  },
} as const;

interface FormValues {
  dataset_id: string;
  model: ModelKind;
  features_csv: string;
  seed: number;
}

const MODEL_KINDS: ModelKind[] = ["logistic_regression", "random_forest"];

function toInput(v: FormValues): RunTrainingInput {
  const list = v.features_csv
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return {
    dataset_id: v.dataset_id.trim(),
    model: v.model,
    features: list.length > 0 ? list : undefined,
    seed: Number(v.seed),
  };
}

function statusColor(
  s: TrainingJob["status"],
): "default" | "primary" | "success" | "error" | "warning" {
  switch (s) {
    case "completed":
      return "success";
    case "failed":
      return "error";
    case "running":
      return "primary";
    case "queued":
      return "warning";
    default:
      return "default";
  }
}

interface TrainingRunSectionProps {
  onTrained?: (job: TrainingJob) => void;
}

export default function TrainingRunSection({ onTrained }: TrainingRunSectionProps) {
  const { control, handleSubmit } = useForm<FormValues>({
    defaultValues: {
      dataset_id: "",
      model: "logistic_regression",
      features_csv: "",
      seed: 42,
    },
  });

  const mutation = useMutation<TrainingJob, Error, FormValues>({
    mutationFn: (v) => runTraining(toInput(v)),
    onSuccess: (job) => onTrained?.(job),
  });

  const job = mutation.data;
  const metrics = job?.metrics ?? null;

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Train Model
        </Typography>

        <Box
          component="form"
          onSubmit={handleSubmit((v) => mutation.mutate(v))}
          sx={{ display: "flex", flexDirection: "column", gap: 2 }}
        >
          <Box sx={styles.grid}>
            <Controller
              name="dataset_id"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  label="Dataset ID"
                  size="small"
                  placeholder="paste id from build above"
                />
              )}
            />
            <Controller
              name="model"
              control={control}
              render={({ field }) => (
                <TextField {...field} select label="Model" size="small">
                  {MODEL_KINDS.map((k) => (
                    <MenuItem key={k} value={k}>
                      {k}
                    </MenuItem>
                  ))}
                </TextField>
              )}
            />
            <Controller
              name="seed"
              control={control}
              render={({ field }) => (
                <TextField {...field} type="number" label="Seed" size="small" />
              )}
            />
            <Controller
              name="features_csv"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  label="Features (comma-separated, blank = all)"
                  size="small"
                  placeholder="rsi_14, ema_20, ..."
                  sx={{ gridColumn: { sm: "1 / -1" } }}
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
              {mutation.isPending ? "Training…" : "Start training"}
            </Button>
          </Box>
        </Box>

        {mutation.isError ? (
          <Alert severity="error" sx={styles.result}>
            {mutation.error.message}
          </Alert>
        ) : null}

        {job ? (
          <Box sx={styles.result}>
            <Box sx={styles.chips}>
              <Chip
                label={`status: ${job.status}`}
                color={statusColor(job.status)}
                size="small"
              />
              <Chip label={`model: ${job.model}`} size="small" />
              <Chip label={`job: ${job.id}`} size="small" />
              {job.model_id ? (
                <Chip
                  label={`model_id: ${job.model_id}`}
                  color="success"
                  size="small"
                />
              ) : null}
              {job.model_version != null ? (
                <Chip label={`v${job.model_version}`} size="small" />
              ) : null}
            </Box>
            {job.error ? (
              <Alert severity="error" sx={{ mb: 1 }}>
                {job.error}
              </Alert>
            ) : null}
            {metrics ? (
              <Box sx={styles.metricRow}>
                <Box sx={styles.metricCell}>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    train acc
                  </Typography>
                  <Typography variant="body2">
                    {metrics.train_accuracy.toFixed(4)}
                  </Typography>
                </Box>
                <Box sx={styles.metricCell}>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    val acc
                  </Typography>
                  <Typography variant="body2">
                    {Number.isNaN(metrics.val_accuracy)
                      ? "—"
                      : metrics.val_accuracy.toFixed(4)}
                  </Typography>
                </Box>
                <Box sx={styles.metricCell}>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    train rows
                  </Typography>
                  <Typography variant="body2">{metrics.train_rows}</Typography>
                </Box>
                <Box sx={styles.metricCell}>
                  <Typography variant="caption" sx={{ color: "text.secondary" }}>
                    val rows
                  </Typography>
                  <Typography variant="body2">{metrics.val_rows}</Typography>
                </Box>
              </Box>
            ) : null}
            <Typography
              variant="caption"
              sx={{ color: "text.secondary", mt: 1, display: "block" }}
            >
              job
            </Typography>
            <Box sx={styles.pre}>{JSON.stringify(job, null, 2)}</Box>
          </Box>
        ) : null}
      </CardContent>
    </Card>
  );
}
