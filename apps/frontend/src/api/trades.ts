import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const TradeRecordSchema = z.object({
  id: z.string(),
  mode: z.enum(["backtest", "paper", "live"]),
  symbol: z.string(),
  side: z.enum(["buy", "sell"]),
  order_id: z.string(),
  signal_id: z.string(),
  strategy: z.string(),
  reason: z.string(),
  ai_confidence: z.string(),
  qty: z.string(),
  fill_price: z.string(),
  fee: z.string(),
  realized_pl: z.string(),
  cash_after: z.string(),
  timestamp_ms: z.number().int(),
});
export type TradeRecord = z.infer<typeof TradeRecordSchema>;

export const TradeListResponseSchema = z.object({
  trades: z.array(TradeRecordSchema),
  total: z.number().int(),
  limit: z.number().int(),
  offset: z.number().int(),
});
export type TradeListResponse = z.infer<typeof TradeListResponseSchema>;

export interface TradeListQuery {
  mode?: "backtest" | "paper" | "live" | "";
  symbol?: string;
  strategy?: string;
  from_ms?: number;
  to_ms?: number;
  limit: number;
  offset: number;
}

function buildParams(q: TradeListQuery): Record<string, string> {
  const out: Record<string, string> = {
    limit: String(q.limit),
    offset: String(q.offset),
  };
  if (q.mode) out.mode = q.mode;
  if (q.symbol) out.symbol = q.symbol;
  if (q.strategy) out.strategy = q.strategy;
  if (q.from_ms != null) out.from_ms = String(q.from_ms);
  if (q.to_ms != null) out.to_ms = String(q.to_ms);
  return out;
}

export async function listTrades(
  q: TradeListQuery,
): Promise<TradeListResponse> {
  const { data } = await api.get<ApiEnvelope<unknown>>("/api/trades", {
    params: buildParams(q),
  });
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return TradeListResponseSchema.parse(data.data);
}
