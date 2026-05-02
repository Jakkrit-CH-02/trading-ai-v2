import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  TextField,
  Typography,
} from "@mui/material";
import { useMutation } from "@tanstack/react-query";
import { Controller, useForm } from "react-hook-form";
import {
  computeFeatures,
  type ComputeFeaturesInput,
  type FeatureMetadata,
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
} as const;

interface FormValues {
  dataset_id: string;
  features_csv: string;
}

function toInput(v: FormValues): ComputeFeaturesInput {
  const list = v.features_csv
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);
  return {
    dataset_id: v.dataset_id.trim(),
    features: list.length > 0 ? list : undefined,
  };
}

export default function ComputeFeaturesSection() {
  const { control, handleSubmit } = useForm<FormValues>({
    defaultValues: { dataset_id: "", features_csv: "" },
  });

  const mutation = useMutation<FeatureMetadata, Error, FormValues>({
    mutationFn: (v) => computeFeatures(toInput(v)),
  });

  return (
    <Card>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 2 }}>
          Compute Features
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
              name="features_csv"
              control={control}
              render={({ field }) => (
                <TextField
                  {...field}
                  label="Features (comma-separated, blank = defaults)"
                  size="small"
                  placeholder="rsi_14, ema_20, ..."
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
              {mutation.isPending ? "Computing…" : "Compute features"}
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
              Features computed — {mutation.data.rows} rows,{" "}
              {mutation.data.features.length} columns.
            </Alert>
            <Box sx={styles.pre}>{JSON.stringify(mutation.data, null, 2)}</Box>
          </Box>
        ) : null}
      </CardContent>
    </Card>
  );
}
