-- Must fail on exactly one shard (a plan with budget 9000 was created via the API),
-- therefore nothing may be committed anywhere.
INSERT INTO schema_migrations(version, description) VALUES ('020', 'budget limit 5000');
ALTER TABLE travel_plans ADD CONSTRAINT budget_limit CHECK (budget <= 5000);
