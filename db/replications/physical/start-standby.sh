#!/usr/bin/env bash
set -euo pipefail
chmod 700 "$PGDATA"
export PGPASSWORD="$REPL_PASSWORD"
if [ ! -s "$PGDATA/PG_VERSION" ]; then
  [[ "$STANDBY_NAME" =~ ^replica[0-9]+$ ]] || { echo 'Invalid standby name'; exit 1; }
  until pg_isready -h postgres -U "$REPL_USER" -d "$POSTGRES_DB" >/dev/null; do sleep 1; done
  create_slot=()
  exists=$(psql -h postgres -U "$REPL_USER" -d "$POSTGRES_DB" -Atc "SELECT 1 FROM pg_replication_slots WHERE slot_name='$STANDBY_NAME'")
  if [ "$exists" != 1 ]; then create_slot=(-C); fi
  pg_basebackup -h postgres -U "$REPL_USER" -D "$PGDATA" -R -X stream "${create_slot[@]}" -S "$STANDBY_NAME" --checkpoint=fast
  printf 'postgres:5432:*:%s:%s\n' "$REPL_USER" "$REPL_PASSWORD" > "$PGDATA/.pgpass"
  chmod 600 "$PGDATA/.pgpass"
  printf "primary_conninfo = 'host=postgres port=5432 user=%s passfile=%s/.pgpass application_name=%s'\n" \
    "$REPL_USER" "$PGDATA" "$STANDBY_NAME" >> "$PGDATA/postgresql.auto.conf"
fi
unset PGPASSWORD
exec postgres -c listen_addresses='*' -c hot_standby=on -c max_connections=100 -c max_worker_processes=10
