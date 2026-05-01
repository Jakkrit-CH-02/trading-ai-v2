import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const SymbolsSchema = z.object({
  symbols: z.array(z.string()),
});
export type SymbolsResponse = z.infer<typeof SymbolsSchema>;

export const BarSchema = z.object({
  symbol: z.string(),
  interval: z.string(),
  open_time: z.number().int(),
  close_time: z.number().int(),
  open: z.string(),
  high: z.string(),
  low: z.string(),
  close: z.string(),
  volume: z.string(),
});
export type Bar = z.infer<typeof BarSchema>;

export const CandlesSchema = z.object({
  symbol: z.string(),
  interval: z.string(),
  bars: z.array(BarSchema),
});
export type CandlesResponse = z.infer<typeof CandlesSchema>;

export const SnapshotSchema = z.object({
  symbol: z.string(),
  interval: z.string(),
  latest: BarSchema,
  source: z.string(),
});
export type SnapshotResponse = z.infer<typeof SnapshotSchema>;

async function unwrap<T>(
  path: string,
  schema: z.ZodSchema<T>,
  params?: Record<string, string | number>,
): Promise<T> {
  const { data } = await api.get<ApiEnvelope<unknown>>(path, { params });
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return schema.parse(data.data);
}

export const getSymbols = (): Promise<SymbolsResponse> =>
  unwrap("/api/market/symbols", SymbolsSchema);

export const getSnapshot = (
  symbol: string,
  interval = "1m",
): Promise<SnapshotResponse> =>
  unwrap("/api/market/snapshot", SnapshotSchema, { symbol, interval });

export const getCandles = (
  symbol: string,
  interval = "1m",
  limit = 30,
): Promise<CandlesResponse> =>
  unwrap("/api/market/candles", CandlesSchema, { symbol, interval, limit });
