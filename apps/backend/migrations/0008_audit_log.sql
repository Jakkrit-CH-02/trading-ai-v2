-- 0008_audit_log.sql
-- Phase 7 — Live Trading Safety. Append-only record of high-risk actions:
-- live order submissions and kill-switch activations.

CREATE TABLE IF NOT EXISTS audit_log (
    id          TEXT        PRIMARY KEY,
    action      TEXT        NOT NULL,
    actor       TEXT        NOT NULL DEFAULT '',
    mode        TEXT        NOT NULL DEFAULT '',
    entity      TEXT        NOT NULL DEFAULT '',
    details     TEXT        NOT NULL DEFAULT '',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created_at ON audit_log (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_log_action ON audit_log (action, created_at DESC);
