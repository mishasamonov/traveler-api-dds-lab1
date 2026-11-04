#!/usr/bin/env bash
# API scale-out: the same Load and Read through nginx over two API instances.
set -euo pipefail
cd "$(dirname "$0")/../.."
L="python scripts/lab6/lab6.py"
$L up sharded --cpus 2.0 --memory 1G --lb
$L benchmark sharded --test load --tag sharded-scaled-2api-load
for i in 1 2 3; do $L benchmark sharded --test read --tag sharded-scaled-2api-read-$i; done
$L stop sharded
$L up baseline --lb
$L benchmark baseline --test load --tag baseline-2api-load
for i in 1 2 3; do $L benchmark baseline --test read --tag baseline-2api-read-$i; done
$L stop baseline
echo "== LB DONE"
