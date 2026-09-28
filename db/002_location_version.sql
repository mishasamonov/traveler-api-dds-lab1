-- Upgrade the baseline database without removing existing travel data.
ALTER TABLE locations ADD COLUMN IF NOT EXISTS version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0);
