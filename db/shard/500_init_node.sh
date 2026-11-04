#!/usr/bin/env bash
# Laboratory 6: one PostgreSQL service = several virtual nodes (databases).
# SHARD_DATABASES lists the databases of this service, e.g. "db_0 db_1 db_2 db_3".
# Every service also has shard_registry: the publisher (postgres_00) owns it,
# the others receive it through logical replication.
set -euo pipefail
for key in APP_USER REPL_USER POSTGRES_USER; do
  value="${!key}"
  [[ "$value" =~ ^[a-z][a-z0-9_]*$ ]] || { echo "Invalid role identifier $key" >&2; exit 1; }
done
admin=(psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER")

"${admin[@]}" -d postgres -v app_user="$APP_USER" -v app_password="$APP_PASSWORD" \
  -v repl_user="$REPL_USER" -v repl_password="$REPL_PASSWORD" <<'SQL'
SELECT format('CREATE ROLE %I LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION', :'app_user', :'app_password') \gexec
SELECT format('CREATE ROLE %I LOGIN REPLICATION PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', :'repl_user', :'repl_password') \gexec
SQL

prepare_database() { # name schema_file
  local db="$1" schema="$2"
  "${admin[@]}" -d postgres -c "CREATE DATABASE $db"
  "${admin[@]}" -d postgres -c "REVOKE ALL ON DATABASE $db FROM PUBLIC"
  "${admin[@]}" -d "$db" -f "$schema"
  "${admin[@]}" -d "$db" -v app_user="$APP_USER" -v repl_user="$REPL_USER" -v db="$db" <<'SQL'
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
SELECT format('GRANT CONNECT ON DATABASE %I TO %I, %I', :'db', :'app_user', :'repl_user') \gexec
SELECT format('GRANT USAGE ON SCHEMA public TO %I, %I', :'app_user', :'repl_user') \gexec
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'repl_user') \gexec
SQL
}

for db in $SHARD_DATABASES; do
  [[ "$db" =~ ^db_[0-9a-f]$ ]] || { echo "Invalid shard database $db" >&2; exit 1; }
  prepare_database "$db" /docker-entrypoint-migrations/001_schema.sql
  "${admin[@]}" -d "$db" -c "COMMENT ON DATABASE $db IS 'TravelerAPI shard ${db#db_}, created on $NODE_NAME'"
  "${admin[@]}" -d "$db" -v app_user="$APP_USER" <<'SQL'
SELECT format('GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO %I', :'app_user') \gexec
SQL
done

# Shared registry of data stores (laboratory 6 additional task).
prepare_database shard_registry /docker-entrypoint-registry/registry.sql
"${admin[@]}" -d shard_registry -v app_user="$APP_USER" <<'SQL'
SELECT format('GRANT SELECT ON ALL TABLES IN SCHEMA public TO %I', :'app_user') \gexec
SQL
if [ "$REGISTRY_ROLE" = publisher ]; then
  "${admin[@]}" -d shard_registry <<'SQL'
INSERT INTO registry_meta(id, version) VALUES (1, 1);
INSERT INTO shard_map(shard, host, port, database)
SELECT s, format('postgres_%s', lpad(((i - 1) / 4)::text, 2, '0')), 5432, 'db_' || s
FROM unnest(string_to_array('0123456789abcdef', NULL)) WITH ORDINALITY AS t(s, i);
CREATE PUBLICATION registry_pub FOR TABLE registry_meta, shard_map, shard_moves;
SQL
else
  for _ in $(seq 1 120); do
    PGPASSWORD="$REPL_PASSWORD" psql -X -h "$REGISTRY_HOST" -U "$REPL_USER" -d shard_registry -Atc \
      "SELECT 1 FROM pg_publication WHERE pubname='registry_pub'" 2>/dev/null | grep -q 1 && break
    sleep 1
  done
  "${admin[@]}" -d shard_registry -v node="$NODE_NAME" \
    -v connection="host=$REGISTRY_HOST port=5432 dbname=shard_registry user=$REPL_USER password=$REPL_PASSWORD application_name=registry_$NODE_NAME" <<'SQL'
SELECT format('CREATE SUBSCRIPTION %I CONNECTION %L PUBLICATION registry_pub WITH (copy_data = true, slot_name = %L)',
  'registry_' || :'node', :'connection', 'registry_' || :'node') \gexec
SQL
fi

cat > "$PGDATA/pg_hba.conf" <<EOF
local all all trust
host all $APP_USER $DOCKER_SUBNET scram-sha-256
host all $REPL_USER $DOCKER_SUBNET scram-sha-256
host replication $REPL_USER $DOCKER_SUBNET scram-sha-256
host all $POSTGRES_USER $DOCKER_SUBNET scram-sha-256
host all all 0.0.0.0/0 reject
host all all ::/0 reject
EOF
echo "Node $NODE_NAME ready: $SHARD_DATABASES + shard_registry ($REGISTRY_ROLE)"
