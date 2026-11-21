# Strategy research log (gate 1) — paused 2026-11-20

Data: BTC, ETH, SOL, BNB, XRP, 1h+4h, 3 years (2023-11 → 2026-11). Costs: fee 0.1%/side, slippage 0.05%/side.
Method: walk-forward 12m train / 3m test, out-of-sample only, all trades through the Risk Engine.
Pooled = equal-weight portfolio of independent per-symbol sleeves (`softtrade backtest --symbols ... --walk-forward`).

## Result: no strategy passes gate 1 (SPEC 11.2) → paper trading (Gate A) is NOT justified

| Strategy | Pooled OOS trades | PF | Expectancy | Notes |
|---|---|---|---|---|
| S1 trend pullback (SPEC) | 94 | 0.67 | −0.28R | win rate 26%; break-even needs ~35% |
| S2 mean reversion | 29 | 0.45 | −0.37R | too few signals |
| S3 breakout | 3 | 0.00 | −0.27R | ~10 raw signals/symbol/3y under SPEC conditions |
| S4 grid | – | – | – | R:R per lot < 1: cannot pass the single-order Risk Engine |

## S1 analysis
- All 69 stop-outs lose ≈ −1.09R; all 23 TP1/trail exits win ≈ +2.06R. Trades held ≤ 6 bars: PF 0.07.
- SOL (PF 0.39) and XRP (0.46) do most of the damage; BNB is the only positive (1.34, 11 trades).
- Costs ≈ 0.30% per round trip ≈ 43% of the loss; gross PnL before costs is already negative.

## Hypotheses tested (pre-registered, one run each, OOS pooled)
1. Confirmation close above previous high: PF 0.57 (worse). Rejected, code reverted.
2. Relative strength vs BTC (30d): PF 0.66 (no change, fewer trades). Rejected, code reverted.
   1+2 together: PF 0.56.
3. Wider stop (`stop_atr` 1.0 / 1.5 / 2.0): PF 0.76 / 0.72 / 0.68. Not a real edge, noise-level difference.

## Conclusion / guidance when resuming
- Do not keep tuning these four strategies: 8+ variants tested, picking the best would be overfitting.
- Next real options: different strategy families, ML/AI scoring (SPEC Phase 6), longer history (> 3y, incl. a bear market), shorter timeframes for more trades.
- Keep gate 1 criteria unchanged; do not relax them to pass.
- Known limitations: pooled sleeves ignore cross-symbol exposure caps; S3 `rr_target` (measured move) is a reference for the R:R check only.

## Plan A (2026-11-21): 7 years of data (2019-12 → 2026-11), strategies unchanged
Same method and costs; SOL only has data from 2020-08. No code or parameter changes (pre-registered: one run each).

| Strategy | Pooled OOS trades | PF | Expectancy | Sharpe | Max DD | Gate 1 |
|---|---|---|---|---|---|---|
| S1 | 459 | 0.93 | −0.05R | −0.21 | 2.4% | FAIL (PF, Sharpe, expectancy) |
| S2 | 64 | 0.23 | −0.52R | −1.47 | 1.8% | FAIL (also < 100 trades) |
| S3 | 9 | 2.04 | +0.22R | 0.29 | 0.1% | FAIL (9 trades: no evidence either way) |

- S1: the 3-year window (PF 0.67) was a bad stretch; over 7 years it is roughly break-even before any edge (win rate 34.4%). Per symbol: ETH 1.14, BNB 1.06, SOL 0.93, BTC 0.81, XRP 0.72. Fees paid 159 USDT vs net −115, so costs alone explain the loss.
- Only 2022 (−1.6%) is a clearly bad year; no year loses > 10% (the yearly criterion passes, because the sleeves are small).
- S2 is negative on every symbol and every regime period: rejected. S3 produces ~1 trade per symbol per 3 years under SPEC conditions: untestable as specified.
- Conclusion: S1 is a break-even strategy, not a Gate 1 candidate; no parameter tuning justified. Next: plan B (different families) and plan C (cost measurement).

## Plan B (2026-11-21): S5 Donchian trend-following — rules fixed BEFORE any run
Different family from S1-S3: slow trend following on 4H, long only (spot), few trades held for days/weeks so fees weigh less.
Textbook constants (Turtle-style), none tuned on our data. One run on 7y pooled walk-forward OOS; whatever comes out is recorded. No variants afterwards.
- Entry (4H close): close > highest high of the previous 55 bars AND close > EMA200 AND BTC regime != TREND_DOWN.
- Stop: entry − 3 × ATR(14) (fixed distance). Exit: Chandelier trailing stop 3 × ATR(22) from entry (no TP1). `rr_target` = entry + 3R, a reference for the Risk Engine's R:R check only.
- S_tech factors (base 60 + 10 each): ADX(14) > 25; BTC regime TREND_UP; volume > 1.5 × 20-bar average; close > EMA50 > EMA200.
- Same costs, filters, Risk Engine and Gate 1 criteria as before. Pass bar unchanged (SPEC 11.2).

### Plan B result (single pre-registered run, 7y pooled walk-forward OOS)
| Strategy | Trades | PF | Expectancy | Sharpe | Max DD | Win rate | Gate 1 |
|---|---|---|---|---|---|---|---|
| S5 Donchian 55 / EMA200 / 3×ATR trail | 447 | 1.41 | +0.16R | 0.76 | 1.3% | 39.1% | FAIL — only Sharpe 0.76 < 1.0 |

- Per symbol all positive: BTC 1.21, ETH 1.25, SOL 1.41, BNB 1.96, XRP 1.19 (82-97 trades each). Yearly: 2021 +1.7%, 2022 +0.2% (bear year survives), 2023 +0.9%, 2024 +0.5%, 2025 +0.9%, 2026 −0.4%. Monte Carlo: p95 max DD 6.0%, final return p5 +20.3% (reordering only).
- First strategy here with a positive out-of-sample edge, but: expectancy +0.16R clears the +0.15R bar by 0.01R (inside noise); Sharpe misses; BNB (PF 1.96) carries a large share; a long-only trend system in 2020-2026 crypto rides market beta.
- NOT a pass. Criteria unchanged, no variant run (pre-registered). Not eligible for paper trading until it passes gate 1.

## Plan C (2026-11-21): cost sensitivity of S5 — scenarios fixed BEFORE running
Question: how much of S5's result depends on the cost assumption? Measurement only; gate criteria stay unchanged and the baseline (fee 0.10%, slippage 0.05%) remains the number of record unless a lower fee is actually obtainable.
Scenarios (per side): fee 0.100% (standard spot taker, baseline), 0.075% (spot with BNB fee discount, obtainable today), 0.050% (needs VIP / futures taker; NOT assumed), × slippage 0.05% (baseline) and 0.02%. Same S5 rules, 7y pooled OOS, one run per cell.

### Plan C result (S5, 7y pooled OOS, 447 trades in every cell)
| fee / side | slippage 0.05% | slippage 0.02% |
|---|---|---|
| 0.100% (baseline) | PF 1.41, +0.16R, Sharpe 0.76 | PF 1.45, +0.17R, Sharpe 0.82 |
| 0.075% (BNB discount) | PF 1.45, +0.17R, Sharpe 0.81 | PF 1.49, +0.18R, Sharpe 0.87 |
| 0.050% (not assumed) | PF 1.48, +0.18R, Sharpe 0.86 | PF 1.53, +0.19R, Sharpe 0.92 |

- Costs move Sharpe by ≤ 0.16 across the whole grid; even the most optimistic cell (0.92) stays below 1.0. Cost is not what blocks gate 1: the strategy's return per unit of risk is.
- The obtainable scenario (BNB discount, 0.075%) is worth about +0.05 Sharpe and +0.01R. Baseline stays the number of record; the live fee should simply be set to the real account rate.
- Remaining option for S5: portfolio-level diversification (more liquid symbols), pre-registered, since the five sleeves are all long-only crypto and highly correlated.
