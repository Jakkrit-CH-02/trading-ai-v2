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
- Next real options: different strategy families, ML/AI scoring (SPEC Phase 5), longer history (> 3y, incl. a bear market), shorter timeframes for more trades.
- Keep gate 1 criteria unchanged; do not relax them to pass.
- Known limitations: pooled sleeves ignore cross-symbol exposure caps; S3 `rr_target` (measured move) is a reference for the R:R check only.
