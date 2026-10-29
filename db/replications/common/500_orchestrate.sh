#!/usr/bin/env bash
set -euo pipefail
for key in APP_USER REPL_USER; do
  value="${!key}"
  [[ "$value" =~ ^[a-z][a-z0-9_]*$ ]] || { echo "Invalid role identifier" >&2; exit 1; }
done
run_dir() {
  local directory="$1" file
  for file in "$directory"/*.sql; do
    [ -e "$file" ] || continue
    psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -f "$file"
  done
  for file in "$directory"/*.sh; do
    [ -e "$file" ] || continue
    bash "$file"
  done
}
run_dir /docker-entrypoint-migrations
psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" \
  -v app_user="$APP_USER" -v app_password="$APP_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'app_user', :'app_password') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT USAGE ON SCHEMA public TO %I', :'app_user') \gexec
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'app_user') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO %I', :'app_user') \gexec
SQL
run_dir /docker-entrypoint-replications
cat > "$PGDATA/pg_hba.conf" <<EOF
local all all trust
host $POSTGRES_DB $APP_USER $DOCKER_SUBNET scram-sha-256
host $POSTGRES_DB $REPL_USER $DOCKER_SUBNET scram-sha-256
host replication $REPL_USER $DOCKER_SUBNET scram-sha-256
host all all 0.0.0.0/0 reject
host all all ::/0 reject
EOF
