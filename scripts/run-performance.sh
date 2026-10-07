#!/usr/bin/env bash
set -euo pipefail
name="${1:-smoke}"
case "$name" in smoke|load|stress|spike|endurance) ;; *) echo 'Expected smoke|load|stress|spike|endurance'; exit 2;; esac
mkdir -p tests/performance-tests/reports
export API_URL="${API_URL:-http://127.0.0.1:4567}"
export TEST_NAME="$name"
export REPORT_DIR=tests/performance-tests/reports
export K6_WEB_DASHBOARD=true
export K6_WEB_DASHBOARD_PORT=-1
export K6_WEB_DASHBOARD_PERIOD=2s
export K6_WEB_DASHBOARD_EXPORT="$REPORT_DIR/$name-dashboard.html"
k6 run --quiet "tests/performance-tests/$name-test.js" 2>&1 | tee "$REPORT_DIR/$name.log"
