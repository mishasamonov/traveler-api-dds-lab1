-- Laboratory 8: a larger data set in a separate database (jsonb_bench) for
-- EXPLAIN, table sizes and WAL per update. Loaded into the relational tables
-- of 001_schema.sql and then migrated with the same 002 + 100 scripts.
--   50 000 plans with 3 locations each (like the laboratory 2 data set)
--   + 3 plans with 20, 100 and 300 locations (document size vs write cost)
-- Location ids end with the last digit of their plan id, as on the shards.
INSERT INTO travel_plans (id, title, description, start_date, end_date, budget, currency, is_public)
SELECT md5('bench-plan-' || i)::uuid, 'Bench trip ' || i, repeat('Travel itinerary ', 8),
       date '2026-06-01' + i % 90, date '2026-06-10' + i % 90, 1000 + i % 500, 'EUR', i % 3 = 0
FROM generate_series(1, 50000) AS i;

INSERT INTO locations (id, travel_plan_id, name, address, latitude, longitude, visit_order, arrival_date, budget, notes)
SELECT overlay(md5('bench-location-' || i || '-' || j) PLACING right(md5('bench-plan-' || i), 1) FROM 32)::uuid,
       md5('bench-plan-' || i)::uuid, 'Location ' || j, 'Street ' || j || ', City ' || i % 100,
       48.8566 + j / 1000.0, 2.3522, j, timestamptz '2026-06-01 10:00+00' + j * interval '1 day', 100, 'Note ' || j
FROM generate_series(1, 50000) AS i CROSS JOIN generate_series(1, 3) AS j;

INSERT INTO travel_plans (id, title, budget, currency)
SELECT md5('bench-big-' || n)::uuid, 'Big plan with ' || n || ' locations', 5000, 'EUR'
FROM unnest(ARRAY[20, 100, 300]) AS n;

INSERT INTO locations (id, travel_plan_id, name, address, latitude, longitude, visit_order, arrival_date, budget, notes)
SELECT overlay(md5('bench-big-' || n || '-' || j) PLACING right(md5('bench-big-' || n), 1) FROM 32)::uuid,
       md5('bench-big-' || n)::uuid, 'Stop ' || j, 'Street ' || j || ', City ' || n,
       48.85 + j / 10000.0, 2.35, j, timestamptz '2026-06-01 10:00+00' + j * interval '1 hour', 50, 'Note ' || j
FROM unnest(ARRAY[20, 100, 300]) AS n CROSS JOIN LATERAL generate_series(1, n) AS j;
