-- 0004_backtest_results.sql
-- Phase 6 — Backtest Engine: durable record of every backtest run, including
-- the config, aggregate metrics, equity curve and per-trade detail.
-- Decimals stored as TEXT to preserve precision (matches trade_log).

CREATE TABLE IF NOT EXISTS backtest_results (
    id                 TEXT        PRIMARY KEY,
    symbol             TEXT        NOT NULL,
    interval           TEXT        NOT NULL,
    strategy_name      TEXT        NOT NULL,
    config_json        JSONB       NOT NULL,

    start_ms           BIGINT      NOT NULL,
    end_ms             BIGINT      NOT NULL,
    bars_processed     INTEGER     NOT NULL DEFAULT 0,

    initial_equity     TEXT        NOT NULL DEFAULT '0',
    final_equity       TEXT        NOT NULL DEFAULT '0',

    total_trades       INTEGER     NOT NULL DEFAULT 0,
    winning_trades     INTEGER     NOT NULL DEFAULT 0,
    losing_trades      INTEGER     NOT NULL DEFAULT 0,

    win_rate           TEXT        NOT NULL DEFAULT '0',
    profit_factor      TEXT        NOT NULL DEFAULT '0',
    total_return       TEXT        NOT NULL DEFAULT '0',
    max_drawdown       TEXT        NOT NULL DEFAULT '0',
    sharpe_ratio       TEXT        NOT NULL DEFAULT '0',

    equity_curve_json  JSONB       NOT NULL DEFAULT '[]'::jsonb,
    trades_json        JSONB       NOT NULL DEFAULT '[]'::jsonb,

    created_ms         BIGINT      NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_backtest_created     ON backtest_results (created_ms DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_symbol      ON backtest_results (symbol, created_ms DESC);
CREATE INDEX IF NOT EXISTS idx_backtest_strategy    ON backtest_results (strategy_name, created_ms DESC);
