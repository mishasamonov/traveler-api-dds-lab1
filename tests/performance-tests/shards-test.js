// Laboratory 7: traffic for the monitoring experiments.
//   MODE=uniform  - plans of all 16 shards (background load, server failure)
//   MODE=hotspot  - only plans whose id ends with HOT_SHARD (one hot virtual node)
// Requests go through both API instances and are tagged with the PostgreSQL
// service that owns the shard in the initial mapping (postgres_00..03).
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { summary } from './utils/summary.js';

const mode = __ENV.MODE || 'uniform';
const hot = (__ENV.HOT_SHARD || '5').toLowerCase();
const ids = new SharedArray(`ids-${mode}-${hot}`, () => JSON.parse(open('./seed.json'))
  .filter(p => mode !== 'hotspot' || p.id.slice(-1) === hot).map(p => p.id));
const bases = (__ENV.API_URLS || 'http://127.0.0.1:4567,http://127.0.0.1:4568').split(',');
const json = { headers: { 'content-type': 'application/json' } };
const serverOf = id => `postgres_0${Math.floor(parseInt(id.slice(-1), 16) / 4)}`;

export const options = {
  scenarios: { traffic: { executor: 'constant-vus', vus: Number(__ENV.VUS || 40), duration: __ENV.DURATION || '120s', gracefulStop: '5s' } },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  // Always-true thresholds only make k6 report every metric separately for each PostgreSQL service.
  thresholds: Object.fromEntries(['postgres_00', 'postgres_01', 'postgres_02', 'postgres_03'].flatMap(s => [
    [`http_reqs{server:${s}}`, ['count>=0']], [`http_req_failed{server:${s}}`, ['rate>=0']], [`http_req_duration{server:${s}}`, ['max>=0']],
  ])),
};

export default function () {
  const base = bases[__VU % bases.length];
  const id = ids[(__VU * 31 + __ITER) % ids.length];
  const tags = { server: serverOf(id), name: 'GET plan' };
  const read = http.get(`${base}/api/travel-plans/${id}`, { tags });
  check(read, { 'read 200': r => r.status === 200 });
  if (read.status === 200 && __ITER % 3 === 0) {
    const plan = read.json();
    const upd = http.put(`${base}/api/travel-plans/${id}`, JSON.stringify({ version: plan.version, budget: (__ITER % 100) + 100 }),
      { ...json, tags: { ...tags, name: 'PUT plan' } });
    check(upd, { 'update 200/409': r => r.status === 200 || r.status === 409 });
  }
  if (mode === 'uniform' && __ITER % 20 === 0) {
    const list = http.get(`${base}/api/travel-plans?page=1&limit=20`, { tags: { server: 'all', name: 'GET list' } });
    check(list, { 'list 200': r => r.status === 200 });
  }
  sleep(0.05);
}

export function handleSummary(data) { return summary(data, `shards-${mode}`); }
