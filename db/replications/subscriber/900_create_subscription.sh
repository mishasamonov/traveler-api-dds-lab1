#!/usr/bin/env bash
set -euo pipefail
until pg_isready -h postgres -U "$REPL_USER" -d "$POSTGRES_DB" >/dev/null; do sleep 1; done
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v app_user="$APP_USER" -v subscription="$SUB_NAME" -v slot="$SUB_NAME" \
  -v connection="host=postgres port=5432 dbname=$POSTGRES_DB user=$REPL_USER password=$REPL_PASSWORD application_name=$SUB_NAME" <<'SQL'
SELECT format('ALTER ROLE %I SET default_transaction_read_only=on', :'app_user') \gexec
SELECT format('CREATE SUBSCRIPTION %I CONNECTION %L PUBLICATION tp_pub WITH (create_slot=true, slot_name=%L, copy_data=true, enabled=true)', :'subscription', :'connection', :'slot') \gexec
SQL
