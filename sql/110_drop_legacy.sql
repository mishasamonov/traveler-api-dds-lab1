-- Laboratory 8, last step of the migration: remove the old relational tables
-- after the JSONB version has been checked (Hurl, k6, API dump).
--   node tools/shard-exec.js /sql/110_drop_legacy.sql
DO $$
BEGIN
  IF to_regclass('public.plan_documents') IS NULL THEN
    RAISE EXCEPTION '%: plan_documents not found, the data would be lost', current_database();
  END IF;
END $$;
DROP TABLE IF EXISTS legacy_locations, legacy_travel_plans;
DROP FUNCTION IF EXISTS touch_plan_updated_at();
SELECT (SELECT count(*) FROM plan_documents) AS plans,
       pg_size_pretty(pg_total_relation_size('plan_documents')) AS plan_documents;
