// Adapted from the instructor's API client. No runtime network imports.
import http from 'k6/http';
import { check } from 'k6';
import { Rate, Counter } from 'k6/metrics';
export const apiErrors = new Rate('api_errors');
export const conflicts = new Counter('expected_version_conflicts');
export function request(method, url, body, status = 200, tags = {}) {
  const response = http.request(method, url, body == null ? null : JSON.stringify(body), {
    headers: { 'Content-Type': 'application/json' }, timeout: '10s',
    tags: { name: `${method} ${url.replace(/\/[0-9a-f-]{36}/g, '/:id').replace(/\?.*/, '')}`, ...tags },
    responseCallback: http.expectedStatuses(status),
  });
  const ok = check(response, { [`${method} expected ${status}`]: r => r.status === status }, tags);
  apiErrors.add(!ok, tags);
  if (response.status === 409 && status === 409) conflicts.add(1, tags);
  return response;
}
export function json(response) {
  try { return response.json(); } catch { return null; }
}
