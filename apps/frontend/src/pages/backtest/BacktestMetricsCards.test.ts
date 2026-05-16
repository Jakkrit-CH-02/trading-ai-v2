import { describe, it, expect } from "vitest";
import { netProfitAbs } from "./BacktestMetricsCards";

describe("netProfitAbs", () => {
  it("returns positive profit when final > initial", () => {
    expect(netProfitAbs("10000", "10842")).toBeCloseTo(842);
  });

  it("returns negative profit when final < initial", () => {
    expect(netProfitAbs("10000", "9500")).toBeCloseTo(-500);
  });

  it("returns zero when equity is unchanged", () => {
    expect(netProfitAbs("10000", "10000")).toBe(0);
  });
});
