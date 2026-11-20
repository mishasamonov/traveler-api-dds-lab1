-- Laboratory 8: relational tables -> JSONB documents on every shard.
--   node tools/shard-exec.js /app/db/migrations/002_plan_documents.sql /sql/100_migrate_to_jsonb.sql [--dry-run]
-- shard-exec runs both files in ONE transaction per database and commits the
-- 16 databases with two-phase commit: the cluster is never half-migrated.

-- 0. Run once: the old tables exist and the documents are still empty.
DO $$
BEGIN
  IF to_regclass('public.travel_plans') IS NULL OR to_regclass('public.locations') IS NULL THEN
    RAISE EXCEPTION '%: travel_plans/locations not found (already migrated?)', current_database();
  END IF;
  IF EXISTS (SELECT 1 FROM plan_documents) THEN
    RAISE EXCEPTION '%: plan_documents is not empty', current_database();
  END IF;
END $$;

-- 1. A writer that was not stopped waits here and fails after the rename;
--    nothing can be written to the old tables after the snapshot below.
LOCK TABLE travel_plans, locations IN EXCLUSIVE MODE;

-- 2. Fingerprint of the relational data (the way back must reproduce it);
--    storage_migrations is created by 002_plan_documents.sql.
INSERT INTO storage_migrations (name, plans, locations, plans_md5, locations_md5)
SELECT 'relational_to_jsonb',
  (SELECT count(*) FROM travel_plans), (SELECT count(*) FROM locations),
  (SELECT md5(coalesce(string_agg(row_to_json(t)::text, E'\n' ORDER BY id), '')) FROM travel_plans t),
  (SELECT md5(coalesce(string_agg(row_to_json(t)::text, E'\n' ORDER BY id), '')) FROM locations t);

-- 3. Backfill: one document per plan, its locations as an array in visit_order.
INSERT INTO plan_documents (id, doc, version, created_at, updated_at)
SELECT p.id,
       jsonb_build_object(
         'title', p.title, 'description', p.description,
         'start_date', p.start_date, 'end_date', p.end_date,
         'budget', p.budget, 'currency', p.currency, 'is_public', p.is_public,
         'locations', coalesce(l.items, '[]'::jsonb)),
       p.version, p.created_at, p.updated_at
FROM travel_plans p
LEFT JOIN LATERAL (
  SELECT jsonb_agg(jsonb_build_object(
           'id', l.id, 'name', l.name, 'address', l.address,
           'latitude', l.latitude, 'longitude', l.longitude, 'visit_order', l.visit_order,
           'arrival_date', l.arrival_date, 'departure_date', l.departure_date,
           'budget', l.budget, 'notes', l.notes, 'version', l.version, 'created_at', l.created_at)
         ORDER BY l.visit_order) AS items
  FROM locations l
  WHERE l.travel_plan_id = p.id
) l ON true;

-- 4. Verification: the documents read back as rows (views of 002) must be
--    exactly the old rows. Any difference aborts this shard and, through
--    shard-exec, all 16.
DO $$
DECLARE plans_diff bigint; locations_diff bigint;
BEGIN
  SELECT count(*) INTO plans_diff FROM (
    (SELECT * FROM travel_plans EXCEPT ALL SELECT * FROM travel_plans_view)
    UNION ALL
    (SELECT * FROM travel_plans_view EXCEPT ALL SELECT * FROM travel_plans)) d;
  SELECT count(*) INTO locations_diff FROM (
    (SELECT * FROM locations EXCEPT ALL SELECT * FROM locations_view)
    UNION ALL
    (SELECT * FROM locations_view EXCEPT ALL SELECT * FROM locations)) d;
  IF plans_diff + locations_diff > 0 THEN
    RAISE EXCEPTION '%: % plan rows and % location rows differ after the backfill',
      current_database(), plans_diff, locations_diff;
  END IF;
END $$;

-- 5. Every role gets on the documents the privileges it had on travel_plans
--    (the API role: SELECT, INSERT, UPDATE, DELETE; the replication role:
--    SELECT for the rebalancing of laboratory 6) and loses the old tables.
DO $$
DECLARE g record;
BEGIN
  FOR g IN
    SELECT grantee, string_agg(privilege_type, ', ') AS privileges
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public' AND table_name = 'travel_plans'
      AND grantee <> (SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'travel_plans')
    GROUP BY grantee
  LOOP
    EXECUTE format('GRANT %s ON plan_documents TO %I', g.privileges, g.grantee);
    EXECUTE format('GRANT SELECT ON travel_plans_view, locations_view TO %I', g.grantee);
    EXECUTE format('REVOKE ALL ON travel_plans, locations FROM %I', g.grantee);
  END LOOP;
END $$;

-- 6. The old tables stay as a backup for a while (sql/110_drop_legacy.sql
--    removes them). Index names are global in a schema, so they are renamed
--    too: the way back can create travel_plans and locations again.
DO $$
DECLARE i record;
BEGIN
  FOR i IN SELECT indexname FROM pg_indexes
           WHERE schemaname = 'public' AND tablename IN ('travel_plans', 'locations') LOOP
    EXECUTE format('ALTER INDEX %I RENAME TO %I', i.indexname, 'legacy_' || i.indexname);
  END LOOP;
END $$;
ALTER TABLE locations RENAME TO legacy_locations;
ALTER TABLE travel_plans RENAME TO legacy_travel_plans;
ANALYZE plan_documents;

-- 7. One result row per shard for the shard-exec table.
SELECT (SELECT count(*) FROM plan_documents) AS plans,
       (SELECT count(*) FROM locations_view) AS locations,
       'rows equal' AS check,
       (SELECT left(plans_md5, 8) FROM storage_migrations ORDER BY migrated_at DESC LIMIT 1) AS plans_md5;
