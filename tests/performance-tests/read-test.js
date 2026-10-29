// Supplemental read-only control. The original mixed lab 2 load stays unchanged.
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import http from 'k6/http';
import { summary } from './utils/summary.js';
const seed = new SharedArray('seed', () => JSON.parse(open('./seed.json')));
const base = __ENV.API_URL || 'http://127.0.0.1:4567';
export const options = {
  scenarios: { reads: { executor: 'constant-vus', vus: 200, duration: '45s', gracefulStop: '10s' } },
  summaryTrendStats: ['avg','med','p(90)','p(95)','p(99)','max'],
  thresholds: { http_req_failed: ['rate<0.01'], checks: ['rate==1'] },
};
export default function () {
  const id = seed[(__VU - 1) % seed.length].id;
  const a=http.get(`${base}/api/travel-plans?page=${1+(__VU%10)}&limit=20`);
  check(a, {'list status 200':r=>r.status===200});
  const b=http.get(`${base}/api/travel-plans/${id}`);
  check(b, {'detail status 200':r=>r.status===200});
}
export function handleSummary(data) { return summary(data,'read'); }
