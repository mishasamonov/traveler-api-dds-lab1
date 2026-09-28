#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

export DATABASE_URL='postgresql://postgres:postgres@127.0.0.1:5433/postgres'
# PGlite is a single-connection test engine; the deployed application uses a regular PostgreSQL pool.
export PG_POOL_MAX=1
"./node_modules/.bin/pglite-server" --db=memory:// --host=127.0.0.1 --port=5433 --max-connections=1 > /tmp/traveler-pglite.log 2>&1 &
db_pid=$!
api_pid=''
cleanup() {
  if [[ -n "$api_pid" ]]; then kill "$api_pid" 2>/dev/null || true; fi
  kill "$db_pid" 2>/dev/null || true
}
trap cleanup EXIT

for _ in {1..50}; do
  if node -e "const {Client}=require('pg');const c=new Client({connectionString:process.env.DATABASE_URL});c.connect().then(()=>c.end()).catch(()=>process.exit(1))" >/dev/null 2>&1; then break; fi
  sleep 0.2
done
node scripts/init-db.js
node src/server.js > /tmp/traveler-api.log 2>&1 &
api_pid=$!
for _ in {1..50}; do
  if curl --silent --fail --noproxy '*' http://127.0.0.1:4567/health >/dev/null 2>&1; then break; fi
  sleep 0.2
done

"./node_modules/.bin/hurl" --test tests/*.hurl --variables-file tests/variables.properties
node --test tests/*.test.js
