-- 0003_trade_log.sql
-- Phase 4 — Trade Log Service: persistent record of every signal/order/fill
-- with reason, AI confidence, and realized P&L.
-- Acceptance: paper/live separable by mode column; PnL recalculable from rows.

CREATE TABLE IF NOT EXISTS trade_log (
    id              TEXT        PRIMARY KEY,
    mode            TEXT        NOT NULL,
    symbol          TEXT        NOT NULL,
    side            TEXT        NOT NULL,
    order_id        TEXT        NOT NULL DEFAULT '',
    signal_id       TEXT        NOT NULL DEFAULT '',
    strategy        TEXT        NOT NULL DEFAULT '',
    reason          TEXT        NOT NULL DEFAULT '',
    ai_confidence   TEXT        NOT NULL DEFAULT '0',
    qty             TEXT        NOT NULL DEFAULT '0',
    fill_price      TEXT        NOT NULL DEFAULT '0',
    fee             TEXT        NOT NULL DEFAULT '0',
    realized_pl     TEXT        NOT NULL DEFAULT '0',
    cash_after      TEXT        NOT NULL DEFAULT '0',
    timestamp_ms    BIGINT      NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_trade_log_ts        ON trade_log (timestamp_ms DESC);
CREATE INDEX IF NOT EXISTS idx_trade_log_symbol_ts ON trade_log (symbol, timestamp_ms DESC);
CREATE INDEX IF NOT EXISTS idx_trade_log_mode_ts   ON trade_log (mode, timestamp_ms DESC);
CREATE INDEX IF NOT EXISTS idx_trade_log_order     ON trade_log (order_id);
CREATE INDEX IF NOT EXISTS idx_trade_log_signal    ON trade_log (signal_id);
