// Laboratory 6 control: only single-shard requests (plan detail by id), no cross-shard list.
import { check } from 'k6';
import { SharedArray } from 'k6/data';
import http from 'k6/http';
import { summary } from './utils/summary.js';
const seed = new SharedArray('seed', () => JSON.parse(open('./seed.json')));
const base = __ENV.API_URL || 'http://127.0.0.1:4567';
export const options = {
  scenarios: { keys: { executor: 'constant-vus', vus: 200, duration: '45s', gracefulStop: '10s' } },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: { http_req_failed: ['rate<0.01'], checks: ['rate==1'] },
};
export default function () {
  const id = seed[(__VU * 7 + __ITER) % seed.length].id;
  check(http.get(`${base}/api/travel-plans/${id}`), { 'detail status 200': r => r.status === 200 });
}
export function handleSummary(data) { return summary(data, 'key'); }
