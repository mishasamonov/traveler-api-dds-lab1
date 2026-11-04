-- DDL + DML on all 16 shards in one distributed transaction.
CREATE TABLE IF NOT EXISTS schema_migrations (
  version TEXT PRIMARY KEY,
  description TEXT NOT NULL,
  applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO schema_migrations(version, description)
VALUES ('010', 'migration registry and partial index for public plans');
CREATE INDEX IF NOT EXISTS idx_plans_public ON travel_plans(created_at DESC) WHERE is_public;
UPDATE travel_plans SET currency = upper(currency) WHERE currency <> upper(currency);
