-- 0001_init.sql
-- Phase 1 placeholder migration. Real schema comes with the trade log + config slices.

CREATE TABLE IF NOT EXISTS schema_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO schema_meta (key, value)
VALUES ('phase', '1-foundation')
ON CONFLICT (key) DO NOTHING;
