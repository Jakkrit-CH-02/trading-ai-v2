import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const BotStateSchema = z.enum([
  "idle",
  "running",
  "paused",
  "halted",
  "error",
]);
export type BotState = z.infer<typeof BotStateSchema>;

export const PositionSchema = z.object({
  id: z.string(),
  symbol: z.string(),
  side: z.enum(["long", "short"]),
  qty: z.string(),
  entry_price: z.string(),
  mark_price: z.string(),
  unrealized_pnl: z.string(),
  opened_at: z.number().int(),
});
export type Position = z.infer<typeof PositionSchema>;

export const DashboardSummarySchema = z.object({
  bot_state: BotStateSchema,
  equity: z.string().nullable(),
  pnl_today: z.string().nullable(),
  open_positions: z.array(PositionSchema),
});
export type DashboardSummary = z.infer<typeof DashboardSummarySchema>;

async function unwrap<T>(path: string, schema: z.ZodSchema<T>): Promise<T> {
  const { data } = await api.get<ApiEnvelope<unknown>>(path);
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return schema.parse(data.data);
}

// TODO: switch to real backend endpoint once /api/dashboard/summary lands.
// Currently served by MSW (src/test/msw/handlers.ts).
export const getDashboardSummary = (): Promise<DashboardSummary> =>
  unwrap("/api/dashboard/summary", DashboardSummarySchema);
