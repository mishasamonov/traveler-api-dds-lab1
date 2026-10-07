#!/usr/bin/env bash
set -uo pipefail
mkdir -p tests/performance-tests/reports
result=0
for name in smoke load stress spike endurance; do
  bash scripts/run-performance.sh "$name"
  code=$?
  printf '%s %s\n' "$name" "$code" >> tests/performance-tests/reports/exit-codes.txt
  # Exit 99 means a performance threshold was crossed: expected evidence for stress/spike.
  if [ "$code" -ne 0 ] && { [ "$code" -ne 99 ] || { [ "$name" != stress ] && [ "$name" != spike ]; }; }; then result=1; fi
  if [ "$name" = smoke ] && [ "$code" -ne 0 ]; then break; fi
done
exit "$result"
