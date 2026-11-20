-- Laboratory 8: the way back, JSONB documents -> relational tables of laboratory 2.
--   node tools/shard-exec.js /app/db/migrations/001_schema.sql /sql/190_rollback_to_relational.sql [--dry-run]
-- 001_schema.sql creates empty travel_plans and locations in the same
-- transaction; the rows come from the views over the documents, so every
-- change made through the JSONB API is kept.
DO $$
BEGIN
  IF to_regclass('public.plan_documents') IS NULL THEN
    RAISE EXCEPTION '%: plan_documents not found', current_database();
  END IF;
  IF EXISTS (SELECT 1 FROM travel_plans) OR EXISTS (SELECT 1 FROM locations) THEN
    RAISE EXCEPTION '%: travel_plans/locations are not empty', current_database();
  END IF;
END $$;
LOCK TABLE plan_documents IN EXCLUSIVE MODE;

INSERT INTO travel_plans SELECT * FROM travel_plans_view;
INSERT INTO locations SELECT * FROM locations_view;

DO $$
BEGIN
  IF (SELECT count(*) FROM travel_plans) <> (SELECT count(*) FROM plan_documents)
     OR (SELECT count(*) FROM locations) <> (SELECT count(*) FROM locations_view) THEN
    RAISE EXCEPTION '%: row counts differ on the way back', current_database();
  END IF;
END $$;

DO $$
DECLARE g record;
BEGIN
  FOR g IN
    SELECT grantee, string_agg(privilege_type, ', ') AS privileges
    FROM information_schema.role_table_grants
    WHERE table_schema = 'public' AND table_name = 'plan_documents'
      AND grantee <> (SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'plan_documents')
    GROUP BY grantee
  LOOP
    EXECUTE format('GRANT %s ON travel_plans, locations TO %I', g.privileges, g.grantee);
  END LOOP;
END $$;

INSERT INTO storage_migrations (name, plans, locations, plans_md5, locations_md5)
SELECT 'jsonb_to_relational',
  (SELECT count(*) FROM travel_plans), (SELECT count(*) FROM locations),
  (SELECT md5(coalesce(string_agg(row_to_json(t)::text, E'\n' ORDER BY id), '')) FROM travel_plans t),
  (SELECT md5(coalesce(string_agg(row_to_json(t)::text, E'\n' ORDER BY id), '')) FROM locations t);

DROP VIEW travel_plans_view, locations_view;
DROP TABLE plan_documents;
DROP FUNCTION plan_document_valid(jsonb, uuid), location_document_valid(jsonb, uuid);
DROP TABLE IF EXISTS legacy_locations, legacy_travel_plans;
ANALYZE travel_plans;
ANALYZE locations;

-- Same fingerprint as before the migration = nothing was lost or changed on the round trip.
SELECT b.plans, b.locations, left(b.plans_md5, 8) AS plans_md5,
       b.plans_md5 = a.plans_md5 AND b.locations_md5 = a.locations_md5 AS same_as_before
FROM (SELECT * FROM storage_migrations WHERE name = 'jsonb_to_relational' ORDER BY migrated_at DESC LIMIT 1) b,
     (SELECT * FROM storage_migrations WHERE name = 'relational_to_jsonb' ORDER BY migrated_at DESC LIMIT 1) a;
