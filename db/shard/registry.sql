-- Shared registry of data stores: which PostgreSQL service owns each of the 16 shards.
-- Written only on postgres_00 (publisher), read by API instances from any copy.
CREATE TABLE registry_meta (
  id INTEGER PRIMARY KEY CHECK (id = 1),
  version BIGINT NOT NULL CHECK (version > 0),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE shard_map (
  shard CHAR(1) PRIMARY KEY CHECK (shard ~ '^[0-9a-f]$'),
  host TEXT NOT NULL,
  port INTEGER NOT NULL DEFAULT 5432,
  database TEXT NOT NULL CHECK (database = 'db_' || shard),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Audit trail of moves performed by tools/rebalance.js.
CREATE TABLE shard_moves (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  shard CHAR(1) NOT NULL,
  from_host TEXT NOT NULL,
  to_host TEXT NOT NULL,
  version BIGINT NOT NULL,
  lock_ms INTEGER,
  moved_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
