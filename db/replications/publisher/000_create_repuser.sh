#!/usr/bin/env bash
set -euo pipefail
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v rep_user="$REPL_USER" -v rep_password="$REPL_PASSWORD" -v db="$POSTGRES_DB" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN REPLICATION PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'rep_user', :'rep_password') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO %I', :'db', :'rep_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'rep_user') \gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'rep_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO %I', :'rep_user') \gexec
SQL
