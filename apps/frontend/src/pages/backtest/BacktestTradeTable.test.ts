// apps/frontend/src/pages/backtest/BacktestTradeTable.test.ts
import { describe, it, expect } from "vitest";
import { pairTrades } from "./BacktestTradeTable";

const makeTrade = (
  side: string,
  price: string,
  pl: string,
  tsMs: number,
) => ({
  signal_id: "sig1",
  order_id: `order-${side}-${tsMs}`,
  symbol: "BTCUSDT",
  side,
  qty: "0.01",
  price,
  realized_pl: pl,
  reason: "crossover",
  timestamp_ms: tsMs,
});

describe("pairTrades", () => {
  it("returns empty array for no trades", () => {
    expect(pairTrades([])).toEqual([]);
  });

  it("pairs a BUY+SELL into one closed round-trip", () => {
    const trades = [
      makeTrade("BUY", "42000", "0", 1000),
      makeTrade("SELL", "43000", "10", 2000),
    ];
    const result = pairTrades(trades);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      id: "order-BUY-1000",
      entryTimeMs: 1000,
      entryPrice: "42000",
      exitTimeMs: 2000,
      exitPrice: "43000",
      qty: "0.01",
      pl: "10",
    });
  });

  it("emits an open round-trip for an unmatched BUY", () => {
    const trades = [makeTrade("BUY", "42000", "0", 1000)];
    const result = pairTrades(trades);
    expect(result).toHaveLength(1);
    expect(result[0]).toMatchObject({
      id: "order-BUY-1000",
      entryTimeMs: 1000,
      entryPrice: "42000",
      exitTimeMs: null,
      exitPrice: null,
      qty: "0.01",
      pl: null,
    });
  });

  it("handles multiple closed round-trips", () => {
    const trades = [
      makeTrade("BUY", "40000", "0", 1000),
      makeTrade("SELL", "41000", "10", 2000),
      makeTrade("BUY", "39000", "0", 3000),
      makeTrade("SELL", "38000", "-10", 4000),
    ];
    const result = pairTrades(trades);
    expect(result).toHaveLength(2);
    expect(result[0].pl).toBe("10");
    expect(result[1].pl).toBe("-10");
  });

  it("handles multiple round-trips with trailing open position", () => {
    const trades = [
      makeTrade("BUY", "40000", "0", 1000),
      makeTrade("SELL", "41000", "10", 2000),
      makeTrade("BUY", "42000", "0", 3000),
    ];
    const result = pairTrades(trades);
    expect(result).toHaveLength(2);
    expect(result[0].pl).toBe("10");
    expect(result[1].pl).toBeNull();
  });
});
