export function summary(data, name) {
  const metrics = data.metrics;
  const lines = [`k6 ${name.toUpperCase()} TEST`, `API: ${__ENV.API_URL || 'http://127.0.0.1:4567'}`, ''];
  for (const key of ['http_reqs', 'iterations', 'checks', 'http_req_failed', 'http_req_duration', 'api_errors', 'expected_version_conflicts']) {
    if (metrics[key]) lines.push(`${key}: ${JSON.stringify(metrics[key].values)}`);
  }
  lines.push('', 'THRESHOLDS');
  for (const [key, metric] of Object.entries(metrics)) {
    for (const [rule, outcome] of Object.entries(metric.thresholds || {}))
      lines.push(`${outcome.ok ? 'PASS' : 'FAIL'} ${key}: ${rule}`);
  }
  const text = lines.join('\n') + '\n';
  const dir = __ENV.RESULT_DIR || 'tests/performance-tests/results';
  return { stdout: text, [`${dir}/${name}-summary.json`]: JSON.stringify(data, null, 2), [`${dir}/${name}-summary.txt`]: text };
}
