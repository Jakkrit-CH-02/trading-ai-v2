-- 0007_alerts.sql
-- Phase 6 — Live Trading Safety. Alert history (drawdown, order rejection,
-- disconnect, slippage, kill events).

CREATE TABLE IF NOT EXISTS alerts (
    id          TEXT        PRIMARY KEY,
    type        TEXT        NOT NULL,
    severity    TEXT        NOT NULL,
    message     TEXT        NOT NULL,
    entity      TEXT        NOT NULL DEFAULT '',
    read        BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_alerts_unread ON alerts (created_at DESC) WHERE read = FALSE;
