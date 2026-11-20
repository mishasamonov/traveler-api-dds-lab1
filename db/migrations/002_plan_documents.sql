-- Laboratory 8: document model in JSONB.
-- One row per travel plan; its locations are embedded in doc->'locations'
-- as an array ordered by visit_order. Columns stay only for what the
-- database itself needs: the key (also the shard key), the optimistic lock
-- version of the plan and the timestamps used for sorting.
--
-- Applied by tools/shard-exec.js together with sql/100_migrate_to_jsonb.sql,
-- by tools/rebalance.js on a new target and by the CI initialisation.

-- "Schemaless" does not mean "no schema": the rules of the relational schema
-- (laboratory 2) are kept as one CHECK. Only immutable operations are used:
-- jsonb operators, regular expressions and numeric casts.
CREATE OR REPLACE FUNCTION location_document_valid(l jsonb, plan_id uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  -- coalesce: a missing key gives NULL, and a CHECK would let NULL through
  SELECT coalesce(jsonb_typeof(l) = 'object'
    -- only known keys
    AND l - ARRAY['id', 'name', 'address', 'latitude', 'longitude', 'visit_order', 'arrival_date',
                  'departure_date', 'budget', 'notes', 'version', 'created_at'] = '{}'::jsonb
    -- co-location of laboratory 6: the location id ends with the shard digit of its plan
    AND l->>'id' ~ '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    AND right(l->>'id', 1) = right(plan_id::text, 1)
    AND jsonb_typeof(l->'name') = 'string' AND length(btrim(l->>'name')) > 0 AND length(l->>'name') <= 200
    AND jsonb_typeof(l->'address') IN ('string', 'null')
    AND jsonb_typeof(l->'notes') IN ('string', 'null')
    AND (jsonb_typeof(l->'latitude') = 'null'
         OR (jsonb_typeof(l->'latitude') = 'number' AND (l->>'latitude')::numeric BETWEEN -90 AND 90))
    AND (jsonb_typeof(l->'longitude') = 'null'
         OR (jsonb_typeof(l->'longitude') = 'number' AND (l->>'longitude')::numeric BETWEEN -180 AND 180))
    AND (jsonb_typeof(l->'budget') = 'null'
         OR (jsonb_typeof(l->'budget') = 'number' AND (l->>'budget')::numeric BETWEEN 0 AND 99999999.99
             AND scale((l->>'budget')::numeric) <= 2))
    AND jsonb_typeof(l->'visit_order') = 'number' AND (l->>'visit_order') ~ '^[1-9][0-9]{0,8}$'
    AND jsonb_typeof(l->'version') = 'number' AND (l->>'version') ~ '^[1-9][0-9]{0,8}$'
    AND jsonb_typeof(l->'arrival_date') IN ('string', 'null')
    AND jsonb_typeof(l->'departure_date') IN ('string', 'null')
    AND jsonb_typeof(l->'created_at') = 'string', false)
$$;

CREATE OR REPLACE FUNCTION plan_document_valid(doc jsonb, plan_id uuid) RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$
  SELECT coalesce(jsonb_typeof(doc) = 'object'
    AND doc - ARRAY['title', 'description', 'start_date', 'end_date', 'budget', 'currency', 'is_public', 'locations'] = '{}'::jsonb
    AND jsonb_typeof(doc->'title') = 'string' AND length(btrim(doc->>'title')) > 0 AND length(doc->>'title') <= 200
    AND jsonb_typeof(doc->'description') IN ('string', 'null')
    AND (jsonb_typeof(doc->'start_date') = 'null' OR doc->>'start_date' ~ '^\d{4}-\d{2}-\d{2}$')
    AND (jsonb_typeof(doc->'end_date') = 'null' OR doc->>'end_date' ~ '^\d{4}-\d{2}-\d{2}$')
    -- ISO dates compare correctly as text
    AND (jsonb_typeof(doc->'start_date') = 'null' OR jsonb_typeof(doc->'end_date') = 'null'
         OR doc->>'end_date' >= doc->>'start_date')
    AND (jsonb_typeof(doc->'budget') = 'null'
         OR (jsonb_typeof(doc->'budget') = 'number' AND (doc->>'budget')::numeric BETWEEN 0 AND 99999999.99
             AND scale((doc->>'budget')::numeric) <= 2))
    AND jsonb_typeof(doc->'currency') = 'string' AND doc->>'currency' ~ '^[A-Z]{3}$'
    AND jsonb_typeof(doc->'is_public') = 'boolean'
    AND jsonb_typeof(doc->'locations') = 'array'
    AND NOT EXISTS (SELECT 1 FROM jsonb_array_elements(doc->'locations') l
                    WHERE NOT location_document_valid(l, plan_id))
    -- the former UNIQUE (travel_plan_id, visit_order) and primary key of locations
    AND (SELECT count(*) = count(DISTINCT l->'visit_order') AND count(*) = count(DISTINCT l->>'id')
         FROM jsonb_array_elements(doc->'locations') l), false)
$$;

CREATE TABLE IF NOT EXISTS plan_documents (
  id UUID PRIMARY KEY,
  doc JSONB NOT NULL,
  version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  CONSTRAINT plan_document_valid CHECK (plan_document_valid(doc, id))
);

-- Phase 1 of the list scatter-gather: ORDER BY created_at DESC, id LIMIT n.
CREATE INDEX IF NOT EXISTS plan_documents_created ON plan_documents (created_at DESC, id);
-- PUT/DELETE /api/locations/:id: find the document that contains the location,
-- doc->'locations' @> '[{"id": "..."}]'. jsonb_path_ops indexes hashes of paths
-- with values only, so it is smaller than the default jsonb_ops and supports @>.
CREATE INDEX IF NOT EXISTS plan_documents_location_ids ON plan_documents USING gin ((doc->'locations') jsonb_path_ops);

-- Relational views over the documents: the verification of the migration, the
-- way back (sql/190_rollback_to_relational.sql) and SQL reports read these.
-- Column names, order and types are those of the laboratory 2 tables.
CREATE OR REPLACE VIEW travel_plans_view AS
SELECT d.id, r.title, r.description, r.start_date, r.end_date, r.budget, r.currency, r.is_public,
       d.version, d.created_at, d.updated_at
FROM plan_documents d,
     jsonb_to_record(d.doc) AS r(title varchar(200), description text, start_date date, end_date date,
                                 budget numeric(10,2), currency varchar(3), is_public boolean);

CREATE OR REPLACE VIEW locations_view AS
SELECT l.id, d.id AS travel_plan_id, l.name, l.address, l.latitude, l.longitude, l.visit_order,
       l.arrival_date, l.departure_date, l.budget, l.notes, l.version, l.created_at
FROM plan_documents d,
     jsonb_to_recordset(d.doc->'locations') AS l(id uuid, name varchar(200), address text, latitude numeric(10,6),
                                                longitude numeric(11,6), visit_order integer, arrival_date timestamptz,
                                                departure_date timestamptz, budget numeric(10,2), notes text,
                                                version integer, created_at timestamptz);

-- Audit of storage migrations (fingerprints of the relational data). Lives in
-- every JSONB database and is moved together with plan_documents by
-- tools/rebalance.js. No serial key: the sequence would not move with the rows.
CREATE TABLE IF NOT EXISTS storage_migrations (
  name text NOT NULL,
  plans integer NOT NULL,
  locations integer NOT NULL,
  plans_md5 text NOT NULL,
  locations_md5 text NOT NULL,
  migrated_at timestamptz NOT NULL DEFAULT clock_timestamp(),
  PRIMARY KEY (name, migrated_at)
);
