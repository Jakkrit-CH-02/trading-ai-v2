import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const BackendHealthSchema = z.object({
  status: z.string(),
  deps: z.object({
    postgres: z.enum(["up", "down"]),
    redis: z.enum(["up", "down"]),
  }),
});
export type BackendHealth = z.infer<typeof BackendHealthSchema>;

export const AIHealthSchema = z.object({
  status: z.string(),
  model_loaded: z.boolean(),
});
export type AIHealth = z.infer<typeof AIHealthSchema>;

async function unwrap<T>(path: string, schema: z.ZodSchema<T>): Promise<T> {
  const { data } = await api.get<ApiEnvelope<unknown>>(path);
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return schema.parse(data.data);
}

export const getBackendHealth = (): Promise<BackendHealth> =>
  unwrap("/healthz", BackendHealthSchema);

export const getAIHealth = (): Promise<AIHealth> =>
  unwrap("/api/ai/healthz", AIHealthSchema);
