import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const AlertSeverity = z.enum(["info", "warning", "critical"]);
export type AlertSeverity = z.infer<typeof AlertSeverity>;

export const AlertTypeSchema = z.enum([
  "drawdown_breach",
  "order_rejection",
  "binance_disconnect",
  "slippage_exceeded",
  "kill_triggered",
]);
export type AlertType = z.infer<typeof AlertTypeSchema>;

export const AlertSchema = z.object({
  id: z.string(),
  type: z.string(),
  severity: AlertSeverity,
  message: z.string(),
  entity: z.string().default(""),
  read: z.boolean(),
  created_at: z.number().int(),
});
export type Alert = z.infer<typeof AlertSchema>;

const AlertListSchema = z.array(AlertSchema);

function unwrap<T>(env: ApiEnvelope<T>): T {
  if (env.error || env.data == null) {
    throw new Error(env.error?.message ?? "empty response");
  }
  return env.data;
}

export async function listAlerts(): Promise<Alert[]> {
  const { data } = await api.get<ApiEnvelope<unknown>>("/api/alerts");
  return AlertListSchema.parse(unwrap(data));
}

export async function ackAlert(id: string): Promise<void> {
  const { data } = await api.post<ApiEnvelope<unknown>>(
    `/api/alerts/${id}/ack`,
  );
  unwrap(data);
}
