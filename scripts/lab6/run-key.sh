#!/usr/bin/env bash
# Single-shard control test (GET plan by id) for four configurations.
set -euo pipefail
cd "$(dirname "$0")/../.."
L="python scripts/lab6/lab6.py"
$L up baseline
for i in 1 2 3; do $L benchmark baseline --test key --tag baseline-key-$i; done
$L up baseline --lb
for i in 1 2 3; do $L benchmark baseline --test key --tag baseline-2api-key-$i; done
$L stop baseline
$L up sharded --cpus 2.0 --memory 1G
for i in 1 2 3; do $L benchmark sharded --test key --tag sharded-scaled-key-$i; done
$L up sharded --cpus 2.0 --memory 1G --lb
for i in 1 2 3; do $L benchmark sharded --test key --tag sharded-scaled-2api-key-$i; done
$L stop sharded
echo "== KEY DONE"
