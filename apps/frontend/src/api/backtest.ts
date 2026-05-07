import { z } from "zod";
import { api, type ApiEnvelope } from "../lib/api";

export const BacktestConfigSchema = z.object({
  symbol: z.string(),
  interval: z.string(),
  strategy_name: z.string(),
  strategy_params: z.record(z.string(), z.string()).nullable().optional(),
  initial_cash: z.string(),
  position_fraction: z.string(),
  stop_loss_pct: z.string(),
  from_ms: z.number().int().optional(),
  to_ms: z.number().int().optional(),
});
export type BacktestConfig = z.infer<typeof BacktestConfigSchema>;

export const BacktestTradeSchema = z.object({
  signal_id: z.string(),
  order_id: z.string(),
  symbol: z.string(),
  side: z.string(),
  qty: z.string(),
  price: z.string(),
  realized_pl: z.string(),
  reason: z.string(),
  timestamp_ms: z.number().int(),
});
export type BacktestTrade = z.infer<typeof BacktestTradeSchema>;

export const EquityPointSchema = z.object({
  timestamp_ms: z.number().int(),
  equity: z.string(),
});
export type EquityPoint = z.infer<typeof EquityPointSchema>;

export const BacktestMetricsSchema = z.object({
  total_trades: z.number().int(),
  winning_trades: z.number().int(),
  losing_trades: z.number().int(),
  win_rate: z.string(),
  profit_factor: z.string(),
  total_return: z.string(),
  max_drawdown: z.string(),
  sharpe_ratio: z.string(),
});
export type BacktestMetrics = z.infer<typeof BacktestMetricsSchema>;

export const BacktestResultSchema = z.object({
  id: z.string(),
  config: BacktestConfigSchema,
  start_ms: z.number().int(),
  end_ms: z.number().int(),
  bars_processed: z.number().int(),
  initial_equity: z.string(),
  final_equity: z.string(),
  metrics: BacktestMetricsSchema,
  equity_curve: z.array(EquityPointSchema),
  trades: z.array(BacktestTradeSchema),
  created_ms: z.number().int(),
});
export type BacktestResult = z.infer<typeof BacktestResultSchema>;

export interface RunBacktestInput {
  symbol: string;
  interval: string;
  strategy_name: string;
  strategy_params?: Record<string, string>;
  initial_cash?: string;
  position_fraction?: string;
  stop_loss_pct?: string;
  from_ms?: number;
  to_ms?: number;
  limit?: number;
}

async function unwrap<T>(
  envelope: ApiEnvelope<unknown>,
  schema: z.ZodSchema<T>,
): Promise<T> {
  if (!envelope || envelope.error || envelope.data == null) {
    throw new Error(envelope?.error?.message ?? "no data");
  }
  return schema.parse(envelope.data);
}

export async function runBacktest(input: RunBacktestInput): Promise<BacktestResult> {
  const { data } = await api.post<ApiEnvelope<unknown>>(
    "/api/backtest/run",
    input,
  );
  return unwrap(data, BacktestResultSchema);
}

export const EvaluationMetricsSchema = z.object({
  total_trades: z.number().int(),
  winning_trades: z.number().int(),
  losing_trades: z.number().int(),
  precision: z.number(),
  recall: z.number(),
  calibration_error: z.number(),
  feature_drift: z.number(),
});
export type EvaluationMetrics = z.infer<typeof EvaluationMetricsSchema>;

export const EvaluationReportSchema = z.object({
  id: z.string(),
  backtest_id: z.string(),
  model_id: z.string(),
  symbol: z.string(),
  interval: z.string(),
  metrics: EvaluationMetricsSchema,
  passed: z.boolean(),
  reason: z.string(),
  created_at_ms: z.number().int(),
});
export type EvaluationReport = z.infer<typeof EvaluationReportSchema>;

export interface RunEvaluationInput {
  backtest_id: string;
  model_id: string;
}

export async function runEvaluation(
  input: RunEvaluationInput,
): Promise<EvaluationReport> {
  const { data } = await api.post<ApiEnvelope<unknown>>(
    "/api/ai/evaluation/run",
    input,
  );
  return unwrap(data, EvaluationReportSchema);
}
