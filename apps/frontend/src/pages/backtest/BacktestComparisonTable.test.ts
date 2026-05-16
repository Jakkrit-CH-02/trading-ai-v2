import { describe, it, expect } from "vitest";
import { computeNetProfit } from "./BacktestComparisonTable";
import type { BacktestResult } from "../../api/backtest";

function makeResult(initial: string, final: string, symbol = "BTCUSDT"): BacktestResult {
  return {
    id: "test-id",
    config: {
      symbol,
      interval: "1h",
      strategy_name: "ma_crossover",
      initial_cash: initial,
      position_fraction: "0.1",
      stop_loss_pct: "0.02",
    },
    start_ms: 1000,
    end_ms: 2000,
    bars_processed: 100,
    initial_equity: initial,
    final_equity: final,
    metrics: {
      total_trades: 5,
      winning_trades: 3,
      losing_trades: 2,
      win_rate: "0.6",
      profit_factor: "1.5",
      total_return: "0.0842",
      max_drawdown: "0.05",
      sharpe_ratio: "1.2",
    },
    equity_curve: [],
    trades: [],
    created_ms: 3000,
  };
}

describe("computeNetProfit", () => {
  it("returns positive profit when final > initial", () => {
    expect(computeNetProfit(makeResult("10000", "10842"))).toBeCloseTo(842);
  });

  it("returns negative profit when final < initial", () => {
    expect(computeNetProfit(makeResult("10000", "9500"))).toBeCloseTo(-500);
  });

  it("returns zero when equity is unchanged", () => {
    expect(computeNetProfit(makeResult("10000", "10000"))).toBe(0);
  });
});
