import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const PaperPositionSchema = z.object({
  symbol: z.string(),
  qty: z.string(),
  avg_entry: z.string(),
  unrealized_pl: z.string(),
  realized_pl: z.string(),
  updated_ms: z.number().int(),
});
export type PaperPosition = z.infer<typeof PaperPositionSchema>;

export const EquityPointSchema = z.object({
  timestamp_ms: z.number().int(),
  equity: z.string(),
});
export type EquityPoint = z.infer<typeof EquityPointSchema>;

export const PerformanceSummarySchema = z.object({
  total_trades: z.number().int(),
  win_trades: z.number().int(),
  loss_trades: z.number().int(),
  win_rate: z.number(),
  total_realized_pl: z.string(),
});
export type PerformanceSummary = z.infer<typeof PerformanceSummarySchema>;

export const PaperPortfolioSchema = z.object({
  initial_balance: z.string(),
  cash: z.string(),
  equity: z.string(),
  realized_pl: z.string(),
  unrealized_pl: z.string(),
  positions: z.array(PaperPositionSchema),
  equity_curve: z.array(EquityPointSchema),
  performance: PerformanceSummarySchema,
  updated_ms: z.number().int(),
});
export type PaperPortfolio = z.infer<typeof PaperPortfolioSchema>;

export const PaperTradeSchema = z.object({
  order_id: z.string(),
  symbol: z.string(),
  side: z.enum(["buy", "sell"]),
  qty: z.string(),
  fill_price: z.string(),
  realized_pl: z.string(),
  cash: z.string(),
  timestamp_ms: z.number().int(),
});
export type PaperTrade = z.infer<typeof PaperTradeSchema>;

export const PaperTradesSchema = z.object({
  trades: z.array(PaperTradeSchema),
});
export type PaperTrades = z.infer<typeof PaperTradesSchema>;

async function unwrap<T>(
  path: string,
  schema: z.ZodType<T, z.ZodTypeDef, unknown>,
  init?: { method?: "get" | "post"; body?: unknown },
): Promise<T> {
  const method = init?.method ?? "get";
  const { data } =
    method === "post"
      ? await api.post<ApiEnvelope<unknown>>(path, init?.body ?? {})
      : await api.get<ApiEnvelope<unknown>>(path);
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return schema.parse(data.data);
}

export const getPaperPortfolio = (): Promise<PaperPortfolio> =>
  unwrap("/api/paper/portfolio", PaperPortfolioSchema);

export const getPaperTrades = (): Promise<PaperTrades> =>
  unwrap("/api/paper/trades", PaperTradesSchema);

export const resetPaperPortfolio = (): Promise<PaperPortfolio> =>
  unwrap("/api/paper/reset", PaperPortfolioSchema, { method: "post" });
