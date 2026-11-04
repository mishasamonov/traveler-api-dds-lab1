#!/usr/bin/env bash
# Second measurement of 4 x 0.5 CPU after the two-phase list query.
# The first measurement (single-phase scatter-gather) is kept as sharded-naive-*.
set -euo pipefail
cd "$(dirname "$0")/../.."
L="python scripts/lab6/lab6.py"
cd evidence/lab6
for f in sharded-equal-*; do mv "$f" "${f/sharded-equal-/sharded-naive-}"; done
cd ../..
$L up sharded --cpus 0.5 --memory 256M
$L seed sharded
python scripts/lab6/verify_list.py
$L benchmark sharded --test load --tag sharded-equal-load
for i in 1 2 3; do $L benchmark sharded --test read --tag sharded-equal-read-$i; done
echo "== registry stage again (fixed --drop-source)"
$L up sharded --cpus 0.5 --memory 256M --source registry
$L seed sharded
python scripts/lab6/demo_rebalance.py rebalance-registry db_3:postgres_03:30 db_7:postgres_02:60 --drop-source
$L hurl sharded --tag rebalance-registry-after
$L stop sharded
echo "== OPTIMIZED DONE"
