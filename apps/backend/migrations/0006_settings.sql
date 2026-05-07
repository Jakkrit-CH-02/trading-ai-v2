-- 0006_settings.sql
-- Phase 6 — Live Trading Safety. Per-user settings (risk thresholds,
-- notification prefs, default symbol/timeframe).

CREATE TABLE IF NOT EXISTS user_settings (
    user_id                 TEXT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    default_symbol          TEXT        NOT NULL DEFAULT 'BTCUSDT',
    default_timeframe       TEXT        NOT NULL DEFAULT '1m',
    max_position_pct        NUMERIC(10,6) NOT NULL DEFAULT 0.02,
    max_daily_drawdown_pct  NUMERIC(10,6) NOT NULL DEFAULT 0.05,
    max_slippage_bps        INT         NOT NULL DEFAULT 30,
    notify_email            BOOLEAN     NOT NULL DEFAULT FALSE,
    notify_webhook_url      TEXT        NOT NULL DEFAULT '',
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
