-- Read-only invariant check: every row must live in the database of its shard.
DO $$
DECLARE bad integer;
BEGIN
  SELECT (SELECT count(*) FROM travel_plans WHERE right(id::text, 1) <> right(current_database(), 1))
       + (SELECT count(*) FROM locations WHERE right(id::text, 1) <> right(current_database(), 1)
            OR right(travel_plan_id::text, 1) <> right(current_database(), 1)) INTO bad;
  IF bad > 0 THEN RAISE EXCEPTION '% rows are stored in a foreign shard %', bad, current_database(); END IF;
END $$;
