# TravelerAPI - laboratory 8: migration to JSONB

Variant 1 of the "structural" laboratory: the storage of the sharded TravelerAPI
(laboratories 6-7: 16 databases `db_0..db_f` on four PostgreSQL services, two API
instances, Prometheus + Grafana) moves from two relational tables to one table of
JSONB documents. The REST API does not change.

| Before (laboratories 2-7) | After (laboratory 8) |
|---------------------------|----------------------|
| `travel_plans` + `locations`, FK, `UNIQUE (travel_plan_id, visit_order) DEFERRABLE` | `plan_documents(id, doc jsonb, version, created_at, updated_at)` |
| plan with locations = 2 queries | 1 indexed read |
| new location = transaction: `FOR UPDATE`, `MAX(visit_order)`, `INSERT` | one atomic `UPDATE ... jsonb_set(...)` |
| reorder = deferred constraint + mass `UPDATE` | change of one array under the row lock |
| rebalance copies and locks 2 tables | 1 data table |

Files:

* [`db/migrations/002_plan_documents.sql`](db/migrations/002_plan_documents.sql) - the
  document table, the CHECK `plan_document_valid` (the rules of the relational schema
  for JSON), the B-tree on `(created_at DESC, id)`, GIN `jsonb_path_ops` on
  `doc->'locations'`, relational views `travel_plans_view` / `locations_view`,
  audit table `storage_migrations`.
* [`sql/100_migrate_to_jsonb.sql`](sql/100_migrate_to_jsonb.sql) - backfill, row-by-row
  verification (the documents read back as rows must equal the old rows), privileges,
  old tables renamed to `legacy_*`.
* [`sql/110_drop_legacy.sql`](sql/110_drop_legacy.sql) - contract step.
* [`sql/120_plpgsql_document_check.sql`](sql/120_plpgsql_document_check.sql) - schema change
  after the migration, applied with 002 while the API runs: the CHECK functions became
  PL/pgSQL (the first SQL-language version was planned again for every UPDATE and took
  1.3 ms of a 1.5 ms update), every stored document is checked with the new version.
* [`sql/190_rollback_to_relational.sql`](sql/190_rollback_to_relational.sql) - the way
  back (with `001_schema.sql`), compares the fingerprint with the one saved before the
  migration.
* [`src/documents.js`](src/documents.js), [`src/app.js`](src/app.js) - API on documents.
* [`tools/shard-exec.js`](tools/shard-exec.js) - several files in one 2PC transaction
  per shard; [`tools/rebalance.js`](tools/rebalance.js) - both layouts.

## Run

```powershell
python scripts/lab8/lab8.py up              # traveler_lab8, API traveler-api:lab7 (relational)
python scripts/lab8/lab8.py seed            # laboratory 2 dataset in 16 shards
python scripts/lab8/lab8.py bench --tag before
python scripts/lab8/lab8.py dump --tag before
python scripts/lab8/lab8.py migrate         # stop API, 002 + 100 on 16 shards (2PC), start traveler-api:lab8
python scripts/lab8/lab8.py dump --tag after # the same md5 of 2 010 API responses
python scripts/lab8/lab8.py rollback-check  # dry run of the way back: same fingerprint on every shard
python scripts/lab8/lab8.py hurl --tag hurl-after
python scripts/lab8/lab8.py check-cost --tag sql   # cost of the CHECK of one UPDATE
docker compose -f docker-compose.lab6.yml -f docker-compose.monitoring.yml -f docker-compose.lab8.yml --profile tools run --rm tools tools/shard-exec.js /app/db/migrations/002_plan_documents.sql /sql/120_plpgsql_document_check.sql
python scripts/lab8/lab8.py bench --tag after
python scripts/lab8/lab8.py explain         # jsonb_bench: sizes, EXPLAIN, WAL per update
python scripts/lab8/lab8.py contract        # drop legacy tables
python scripts/lab8/lab8.py rebalance       # move db_3 and db_7 under load (JSONB layout)
```

Grafana: <http://127.0.0.1:3001> (port 3001 in this laboratory), Prometheus:
<http://127.0.0.1:9090>. Results and screenshots: [`evidence/lab8`](evidence/lab8).

CI (`TravelerAPI tests`): [`scripts/lab8/ci-init.js`](scripts/lab8/ci-init.js) runs the
whole path on 16 databases (relational schema, dataset, migration with its check,
way back in a rolled-back transaction, contract), then all Hurl files and the
concurrency tests run against the JSONB API.
