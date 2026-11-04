-- Refused before connecting: the tool controls BEGIN/PREPARE/COMMIT itself.
BEGIN;
UPDATE travel_plans SET is_public = true;
COMMIT;
