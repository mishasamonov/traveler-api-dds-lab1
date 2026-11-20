-- Laboratory 8, schema change after the migration: the CHECK functions of
-- plan_documents are now PL/pgSQL (see db/migrations/002_plan_documents.sql).
--   node tools/shard-exec.js /app/db/migrations/002_plan_documents.sql /sql/120_plpgsql_document_check.sql
-- 002 is idempotent, so applying it again replaces the functions; the API keeps
-- running (CREATE OR REPLACE FUNCTION does not lock plan_documents).
-- A CHECK is not re-evaluated for existing rows when its function changes,
-- so every stored document is checked with the new version here; one
-- rejected document rolls back all 16 shards.
--
-- The check runs with an EMPTY search_path, like the table synchronisation
-- worker of logical replication (tools/rebalance.js) and pg_restore: a
-- function that calls another one without the schema name fails here.
SET LOCAL search_path = '';
DO $$
DECLARE bad bigint;
BEGIN
  SELECT count(*) INTO bad FROM public.plan_documents WHERE NOT public.plan_document_valid(doc, id);
  IF bad > 0 THEN
    RAISE EXCEPTION '%: % documents are rejected by the new plan_document_valid', current_database(), bad;
  END IF;
END $$;

SELECT (SELECT count(*) FROM public.plan_documents) AS documents,
       'all valid' AS check,
       (SELECT l.lanname FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_language l ON l.oid = p.prolang
        WHERE p.proname = 'plan_document_valid') AS language,
       pg_catalog.current_setting('search_path') AS search_path;
