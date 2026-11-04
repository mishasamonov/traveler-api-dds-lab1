-- Laboratory 2 dataset (2000 plans, 6000 locations) split across the 16 shards.
-- Applied with tools/shard-exec.js: every database keeps only the rows whose
-- shard key (last hex digit of the plan id) equals the last character of its name.
TRUNCATE locations, travel_plans;
INSERT INTO travel_plans(id, title, description, budget, currency)
SELECT md5('lab2-plan-' || i)::uuid, 'Baseline trip ' || i, repeat('Travel itinerary ', 8), 1000, 'EUR'
FROM generate_series(1, 2000) AS i
WHERE right(md5('lab2-plan-' || i), 1) = right(current_database(), 1);
-- Location ids end with the same digit as the plan: co-located and routable by id alone.
INSERT INTO locations(id, travel_plan_id, name, visit_order, latitude, longitude, budget)
SELECT overlay(md5('lab2-location-' || i || '-' || j) PLACING right(md5('lab2-plan-' || i), 1) FROM 32)::uuid,
  md5('lab2-plan-' || i)::uuid, 'Location ' || j, j, 48.8566, 2.3522, 100
FROM generate_series(1, 2000) AS i CROSS JOIN generate_series(1, 3) AS j
WHERE right(md5('lab2-plan-' || i), 1) = right(current_database(), 1);
ANALYZE travel_plans;
ANALYZE locations;
