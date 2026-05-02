import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const LabelKindSchema = z.enum([
  "next_direction",
  "future_return",
  "threshold_move",
]);
export type LabelKind = z.infer<typeof LabelKindSchema>;

export const LabelConfigSchema = z.object({
  kind: LabelKindSchema,
  horizon: z.number().int().min(1),
  threshold: z.number(),
});
export type LabelConfig = z.infer<typeof LabelConfigSchema>;

export const SplitConfigSchema = z.object({
  train: z.number(),
  val: z.number(),
  test: z.number(),
});
export type SplitConfig = z.infer<typeof SplitConfigSchema>;

export const DatasetMetadataSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  timeframe: z.string(),
  from_ms: z.number().int(),
  to_ms: z.number().int(),
  rows: z.number().int(),
  label: LabelConfigSchema,
  split: SplitConfigSchema,
  path: z.string(),
  created_at_ms: z.number().int(),
});
export type DatasetMetadata = z.infer<typeof DatasetMetadataSchema>;

const BuildResponseSchema = z.object({ dataset: DatasetMetadataSchema });

export const FeatureMetadataSchema = z.object({
  dataset_id: z.string(),
  path: z.string(),
  rows: z.number().int(),
  features: z.array(z.string()),
  created_at_ms: z.number().int(),
});
export type FeatureMetadata = z.infer<typeof FeatureMetadataSchema>;

const ComputeResponseSchema = z.object({ features: FeatureMetadataSchema });

export interface BuildDatasetInput {
  symbol: string;
  timeframe: string;
  from_ms: number;
  to_ms: number;
  label: LabelConfig;
  split: SplitConfig;
}

async function unwrap<T>(
  path: string,
  body: unknown,
  schema: z.ZodSchema<T>,
): Promise<T> {
  const { data } = await api.post<ApiEnvelope<unknown>>(path, body);
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return schema.parse(data.data);
}

export const buildDataset = (input: BuildDatasetInput): Promise<DatasetMetadata> =>
  unwrap("/api/ai/datasets/build", input, BuildResponseSchema).then(
    (r) => r.dataset,
  );

export interface ComputeFeaturesInput {
  dataset_id: string;
  features?: string[];
}

export const computeFeatures = (
  input: ComputeFeaturesInput,
): Promise<FeatureMetadata> =>
  unwrap("/api/ai/features/compute", input, ComputeResponseSchema).then(
    (r) => r.features,
  );

// ---------- Training ----------

export const ModelKindSchema = z.enum(["logistic_regression", "random_forest"]);
export type ModelKind = z.infer<typeof ModelKindSchema>;

export const JobStatusSchema = z.enum([
  "queued",
  "running",
  "completed",
  "failed",
  "cancelled",
]);
export type JobStatus = z.infer<typeof JobStatusSchema>;

export const TrainingMetricsSchema = z.object({
  train_rows: z.number().int(),
  val_rows: z.number().int(),
  train_accuracy: z.number(),
  val_accuracy: z.number(),
  classes: z.array(z.number().int()),
});
export type TrainingMetrics = z.infer<typeof TrainingMetricsSchema>;

export const TrainingJobSchema = z.object({
  id: z.string(),
  status: JobStatusSchema,
  dataset_id: z.string(),
  model: ModelKindSchema,
  features: z.array(z.string()),
  window: z
    .object({ from_ms: z.number().int(), to_ms: z.number().int() })
    .nullable()
    .optional(),
  metrics: TrainingMetricsSchema.nullable().optional(),
  model_path: z.string().nullable().optional(),
  metadata_path: z.string().nullable().optional(),
  model_id: z.string().nullable().optional(),
  model_version: z.number().int().nullable().optional(),
  error: z.string().nullable().optional(),
  created_at_ms: z.number().int(),
  completed_at_ms: z.number().int().nullable().optional(),
});
export type TrainingJob = z.infer<typeof TrainingJobSchema>;

const TrainingRunResponseSchema = z.object({ job: TrainingJobSchema });

export interface RunTrainingInput {
  dataset_id: string;
  model: ModelKind;
  features?: string[];
  seed?: number;
}

export const runTraining = (input: RunTrainingInput): Promise<TrainingJob> =>
  unwrap("/api/ai/training/run", input, TrainingRunResponseSchema).then(
    (r) => r.job,
  );

// ---------- Models registry ----------

export const EnvironmentSchema = z.enum(["paper", "live"]);
export type Environment = z.infer<typeof EnvironmentSchema>;

export const ModelMetadataSchema = z.object({
  id: z.string(),
  version: z.number().int(),
  dataset_id: z.string(),
  feature_schema_id: z.string().nullable().optional(),
  feature_names: z.array(z.string()),
  metrics: z.record(z.string(), z.number()),
  artifact_path: z.string(),
  created_at_ms: z.number().int(),
  evaluated: z.boolean(),
});
export type ModelMetadata = z.infer<typeof ModelMetadataSchema>;

export const ActiveModelsSchema = z.object({
  paper: z.string().nullable().optional(),
  live: z.string().nullable().optional(),
});
export type ActiveModels = z.infer<typeof ActiveModelsSchema>;

const ListModelsResponseSchema = z.object({
  models: z.array(ModelMetadataSchema),
  active: ActiveModelsSchema,
});
export type ListModelsResponse = z.infer<typeof ListModelsResponseSchema>;

export async function listModels(): Promise<ListModelsResponse> {
  const { data } = await api.get<ApiEnvelope<unknown>>("/api/ai/models");
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return ListModelsResponseSchema.parse(data.data);
}

const PromoteResponseSchema = z.object({
  active: ActiveModelsSchema,
  environment: EnvironmentSchema,
  model_id: z.string(),
});

export const promoteModel = (
  modelId: string,
  environment: Environment,
): Promise<z.infer<typeof PromoteResponseSchema>> =>
  unwrap(`/api/ai/models/${modelId}/promote`, { environment }, PromoteResponseSchema);

// ---------- Predict ----------

export const SignalSchema = z.enum(["BUY", "SELL", "HOLD"]);
export type Signal = z.infer<typeof SignalSchema>;

export const FeatureContributionSchema = z.object({
  name: z.string(),
  value: z.number(),
  importance: z.number(),
  contribution: z.number(),
});
export type FeatureContribution = z.infer<typeof FeatureContributionSchema>;

export const ExplanationSchema = z.object({
  reason: z.string(),
  top_features: z.array(z.string()),
  contributions: z.array(FeatureContributionSchema),
  confidence_explanation: z.string(),
});
export type Explanation = z.infer<typeof ExplanationSchema>;

export const PredictResponseSchema = z.object({
  symbol: z.string(),
  timeframe: z.string(),
  signal: SignalSchema,
  confidence: z.number(),
  risk_score: z.number(),
  probabilities: z.record(z.string(), z.number()),
  model_id: z.string(),
  model_version: z.number().int(),
  reason: z.string(),
  cached: z.boolean(),
  explanation: ExplanationSchema.nullable().optional(),
});
export type PredictResponse = z.infer<typeof PredictResponseSchema>;

export interface PredictInput {
  symbol: string;
  timeframe: string;
  features: Record<string, number>;
  environment?: Environment;
}

export async function predict(
  input: PredictInput,
  explain = false,
): Promise<PredictResponse> {
  const path = explain ? "/api/ai/predict?explain=true" : "/api/ai/predict";
  const { data } = await api.post<ApiEnvelope<unknown>>(path, input);
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return PredictResponseSchema.parse(data.data);
}

export async function reloadModel(): Promise<{ loaded: boolean }> {
  const { data } = await api.post<ApiEnvelope<{ loaded: boolean }>>(
    "/api/ai/predict/reload",
  );
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return { loaded: Boolean((data.data as { loaded: boolean }).loaded) };
}
