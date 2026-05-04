import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const RiskPositionSchema = z.object({
  symbol: z.string(),
  qty: z.string(),
  avg_entry: z.string(),
  notional_pct: z.string(),
  unrealized_pl: z.string(),
  realized_pl: z.string(),
});
export type RiskPosition = z.infer<typeof RiskPositionSchema>;

export const RiskSnapshotSchema = z.object({
  state: z.string(),
  max_position_pct: z.string(),
  max_daily_drawdown_pct: z.string(),
  max_slippage_bps: z.number().int(),
  equity: z.string(),
  initial_equity: z.string(),
  cash: z.string(),
  exposure: z.string(),
  exposure_pct: z.string(),
  daily_pnl: z.string(),
  daily_drawdown_pct: z.string(),
  open_positions: z.number().int(),
  largest_position_pct: z.string(),
  positions: z.array(RiskPositionSchema),
  updated_ms: z.number().int(),
});
export type RiskSnapshot = z.infer<typeof RiskSnapshotSchema>;

export async function getRiskSnapshot(): Promise<RiskSnapshot> {
  const { data } =
    await api.get<ApiEnvelope<unknown>>("/api/risk/snapshot");
  if (!data || data.error || data.data == null) {
    throw new Error(data?.error?.message ?? "no data");
  }
  return RiskSnapshotSchema.parse(data.data);
}
