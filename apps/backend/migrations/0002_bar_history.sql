-- 0002_bar_history.sql
-- Phase 1 — Market Data: persistent OHLCV history.
-- Acceptance criteria: candles unique by (symbol, interval, open_time).

CREATE TABLE IF NOT EXISTS bar_history (
    symbol      TEXT        NOT NULL,
    interval    TEXT        NOT NULL,
    open_time   BIGINT      NOT NULL,
    close_time  BIGINT      NOT NULL,
    open        TEXT        NOT NULL,
    high        TEXT        NOT NULL,
    low         TEXT        NOT NULL,
    close       TEXT        NOT NULL,
    volume      TEXT        NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (symbol, interval, open_time)
);

CREATE INDEX IF NOT EXISTS idx_bar_history_lookup
    ON bar_history (symbol, interval, open_time DESC);
