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
