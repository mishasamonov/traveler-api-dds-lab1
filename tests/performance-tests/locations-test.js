// Laboratory 8: the location operations, whose SQL changed most with JSONB.
// Every VU owns one seeded plan (3 locations) and repeats:
//   GET plan -> PUT its first location -> POST a new location -> DELETE it.
// The plan keeps 3 locations, so the document size stays the same during the test.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { summary } from './utils/summary.js';

const seed = new SharedArray('seed', () => JSON.parse(open('./seed.json')));
const base = __ENV.API_URL || 'http://127.0.0.1:4567';
const json = { headers: { 'content-type': 'application/json' } };
const OPS = ['GET plan', 'PUT location', 'POST location', 'DELETE location'];

export const options = {
  scenarios: { locations: { executor: 'constant-vus', vus: Number(__ENV.VUS || 50), duration: __ENV.DURATION || '60s', gracefulStop: '10s' } },
  summaryTrendStats: ['avg', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.01'], checks: ['rate>0.99'],
    // Always-true thresholds: k6 then reports every operation separately.
    ...Object.fromEntries(OPS.map(op => [`http_req_duration{name:${op}}`, ['max>=0']])),
  },
};

export default function () {
  const id = seed[(__VU - 1) % seed.length].id;
  const read = http.get(`${base}/api/travel-plans/${id}`, { tags: { name: 'GET plan' } });
  if (!check(read, { 'GET plan 200': r => r.status === 200 })) { sleep(0.5); return; }
  const loc = read.json().locations[0];
  const upd = http.put(`${base}/api/locations/${loc.id}`, JSON.stringify({ version: loc.version, notes: `iteration ${__ITER}` }),
    { ...json, tags: { name: 'PUT location' } });
  check(upd, { 'PUT location 200': r => r.status === 200 });
  const add = http.post(`${base}/api/travel-plans/${id}/locations`, JSON.stringify({ name: `k6 stop ${__ITER}`, budget: 10 }),
    { ...json, tags: { name: 'POST location' } });
  if (check(add, { 'POST location 201': r => r.status === 201 })) {
    const del = http.del(`${base}/api/locations/${add.json().id}`, null, { tags: { name: 'DELETE location' } });
    check(del, { 'DELETE location 204': r => r.status === 204 });
  }
  sleep(0.05);
}

export function handleSummary(data) { return summary(data, 'locations'); }
