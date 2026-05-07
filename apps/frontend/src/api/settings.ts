import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const SettingsSchema = z.object({
  user_id: z.string().default(""),
  default_symbol: z.string().min(1),
  default_timeframe: z.enum(["1m", "5m", "15m", "1h", "4h", "1d"]),
  default_mode: z.enum(["paper", "live"]).default("paper"),
  max_position_pct: z.string(),
  max_daily_drawdown_pct: z.string(),
  max_slippage_bps: z.number().int().nonnegative().max(10_000),
  notify_email: z.boolean(),
  notify_webhook_url: z.string(),
  updated_at: z.number().int().default(0),
});
export type Settings = z.infer<typeof SettingsSchema>;

export const ApiKeyStatusSchema = z.object({
  configured: z.boolean(),
  masked_key: z.string().default(""),
  permissions: z.object({
    read: z.boolean().default(false),
    spot_trade: z.boolean().default(false),
    withdraw: z.boolean().default(false),
  }),
  testnet: z.boolean().default(true),
  last_checked_ms: z.number().int().default(0),
});
export type ApiKeyStatus = z.infer<typeof ApiKeyStatusSchema>;

function unwrap<T>(env: ApiEnvelope<T>): T {
  if (env.error || env.data == null) {
    throw new Error(env.error?.message ?? "empty response");
  }
  return env.data;
}

export async function getSettings(): Promise<Settings> {
  const { data } = await api.get<ApiEnvelope<unknown>>("/api/settings");
  return SettingsSchema.parse(unwrap(data));
}

export async function updateSettings(input: Settings): Promise<Settings> {
  const { data } = await api.put<ApiEnvelope<unknown>>("/api/settings", input);
  return SettingsSchema.parse(unwrap(data));
}

export async function getApiKeyStatus(): Promise<ApiKeyStatus> {
  const { data } = await api.get<ApiEnvelope<unknown>>(
    "/api/settings/binance-key/status",
  );
  return ApiKeyStatusSchema.parse(unwrap(data));
}

export async function testApiKey(): Promise<ApiKeyStatus> {
  const { data } = await api.post<ApiEnvelope<unknown>>(
    "/api/settings/binance-key/test",
  );
  return ApiKeyStatusSchema.parse(unwrap(data));
}
