#!/usr/bin/env bash
set -euo pipefail
node src/server.js &
api_pid=$!
trap 'kill "$api_pid" 2>/dev/null || true' EXIT
for _ in {1..50}; do
  if curl --silent --fail --noproxy '*' http://127.0.0.1:4567/health >/dev/null 2>&1; then break; fi
  sleep 0.2
done
npm run test:hurl
npm test
