import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const BotStateSchema = z.enum(["idle", "running", "paused", "halted"]);
export type BotState = z.infer<typeof BotStateSchema>;

export const BotModeSchema = z.enum(["backtest", "paper", "live"]);
export type BotMode = z.infer<typeof BotModeSchema>;

export const BotSignalSchema = z.object({
  id: z.string().default(""),
  action: z.string().default(""),
  symbol: z.string().default(""),
});

export const BotStatusSchema = z.object({
  state: BotStateSchema,
  mode: BotModeSchema,
  symbol: z.string(),
  last_signal: BotSignalSchema.partial().optional(),
  last_error: z.string().default(""),
});
export type BotStatus = z.infer<typeof BotStatusSchema>;

export const StartRequestSchema = z.object({
  mode: BotModeSchema,
  strategy: z.enum(["ma_cross", "rsi", "ai"]),
  symbol: z.string().min(1),
  timeframe: z.enum(["1m", "5m", "15m", "1h", "4h", "1d"]),
  risk: z.object({
    max_position_pct: z.number().positive().max(1),
    max_daily_drawdown_pct: z.number().positive().max(1),
    max_slippage_bps: z.number().int().nonnegative().max(10_000),
    stop_loss_fraction: z.number().positive().max(1),
  }),
  confirmed: z.boolean().optional(),
});
export type StartRequest = z.infer<typeof StartRequestSchema>;

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

export const getBotStatus = (): Promise<BotStatus> =>
  unwrap("/api/bot/status", BotStatusSchema);

export const startBot = (req: StartRequest): Promise<BotStatus> =>
  unwrap("/api/bot/start", BotStatusSchema, { method: "post", body: req });

export const stopBot = (): Promise<BotStatus> =>
  unwrap("/api/bot/stop", BotStatusSchema, { method: "post" });

export const pauseBot = (): Promise<BotStatus> =>
  unwrap("/api/bot/pause", BotStatusSchema, { method: "post" });
