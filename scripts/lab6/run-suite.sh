#!/usr/bin/env bash
# Full laboratory 6 sequence. Each stage starts from fresh traveler_lab6* volumes.
set -euo pipefail
cd "$(dirname "$0")/../.."
L="python scripts/lab6/lab6.py"

echo "== 1. sharded, 4 x 0.5 CPU / 256 MiB (same total as baseline)"
$L up sharded --cpus 0.5 --memory 256M
$L seed sharded
$L distribution sharded --tag distribution
python scripts/lab6/topology.py
$L hurl sharded --tag sharded
$L concurrency --tag sharded
python scripts/lab6/demo_tools.py
$L benchmark sharded --test load --tag sharded-equal-load
for i in 1 2 3; do $L benchmark sharded --test read --tag sharded-equal-read-$i; done

echo "== 2. rebalance under load, mapping file"
$L up sharded --cpus 0.5 --memory 256M --source file
$L seed sharded
python scripts/lab6/demo_rebalance.py rebalance-file db_3:postgres_03:30 db_7:postgres_02:60
$L hurl sharded --tag rebalance-file-after

echo "== 3. rebalance under load, shared registry"
$L up sharded --cpus 0.5 --memory 256M --source registry
$L seed sharded
python scripts/lab6/demo_rebalance.py rebalance-registry db_3:postgres_03:30 db_7:postgres_02:60 --drop-source
$L hurl sharded --tag rebalance-registry-after

echo "== 4. sharded, 4 x 2 CPU / 1 GiB (each node like the baseline)"
$L up sharded --cpus 2.0 --memory 1G
$L benchmark sharded --test load --tag sharded-scaled-load
for i in 1 2 3; do $L benchmark sharded --test read --tag sharded-scaled-read-$i; done
$L stop sharded

echo "== 5. baseline: laboratory 4 API, one PostgreSQL 2 CPU / 1 GiB"
$L up baseline
$L seed baseline
$L hurl baseline --tag baseline
$L benchmark baseline --test load --tag baseline-load
for i in 1 2 3; do $L benchmark baseline --test read --tag baseline-read-$i; done
$L stop baseline
echo "== SUITE DONE"
