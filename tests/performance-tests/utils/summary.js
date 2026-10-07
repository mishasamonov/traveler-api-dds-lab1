import { textSummary } from '../vendor/k6-summary.js';
export function handleSummary(data) {
  const dir = __ENV.REPORT_DIR || 'tests/performance-tests/reports';
  const name = __ENV.TEST_NAME || 'test';
  return {
    [`${dir}/${name}-summary.json`]: JSON.stringify(data, null, 2),
    stdout: textSummary(data, { indent: ' ', enableColors: false }),
  };
}
