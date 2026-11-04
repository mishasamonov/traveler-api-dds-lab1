// Laboratory 6: constant traffic through both API instances while shards move.
// Every request is tagged with the shard of its plan, so the write freeze of
// one moving database can be separated from the other 15.
import http from 'k6/http';
import { check, sleep } from 'k6';
import { SharedArray } from 'k6/data';
import { summary } from './utils/summary.js';

const seed = new SharedArray('seed', () => JSON.parse(open('./seed.json')));
const bases = (__ENV.API_URLS || 'http://127.0.0.1:4567,http://127.0.0.1:4568').split(',');
const duration = __ENV.DURATION || '100s';
const json = { headers: { 'content-type': 'application/json' } };

export const options = {
  scenarios: { rebalance: { executor: 'constant-vus', vus: Number(__ENV.VUS || 60), duration, gracefulStop: '10s' } },
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
  thresholds: {
    http_req_failed: ['rate<0.01'], checks: ['rate>0.99'],
    'http_req_duration{shard:3}': ['max>=0'], 'http_req_failed{shard:3}': ['rate<0.01'],
    'http_req_duration{shard:7}': ['max>=0'], 'http_req_failed{shard:7}': ['rate<0.01'],
    'http_req_duration{shard:other}': ['max>=0'], 'http_req_failed{shard:other}': ['rate<0.01'],
  },
};

let plan;
export default function () {
  const base = bases[__VU % bases.length];
  const id = seed[(__VU - 1) % seed.length].id;
  const last = id.slice(-1);
  const tags = { shard: last === '3' || last === '7' ? last : 'other', api: String(__VU % bases.length + 1) };
  const read = http.get(`${base}/api/travel-plans/${id}`, { tags: { ...tags, name: 'GET plan' } });
  check(read, { 'read 200': r => r.status === 200 });
  if (read.status === 200) plan = read.json();
  if (plan) {
    const upd = http.put(`${base}/api/travel-plans/${id}`, JSON.stringify({ version: plan.version, budget: (__ITER % 100) + 100 }),
      { ...json, tags: { ...tags, name: 'PUT plan' } });
    check(upd, { 'update 200': r => r.status === 200 });
    const loc = plan.locations && plan.locations[0];
    if (loc) {
      const l = http.put(`${base}/api/locations/${loc.id}`, JSON.stringify({ version: loc.version, notes: `iteration ${__ITER}` }),
        { ...json, tags: { ...tags, name: 'PUT location' } });
      check(l, { 'location 200': r => r.status === 200 });
    }
  }
  if (__ITER % 10 === 0) {
    const c = http.post(`${base}/api/travel-plans`, JSON.stringify({ title: `k6 rebalance ${__VU} ${__ITER}` }), { ...json, tags: { shard: 'new', name: 'POST plan' } });
    check(c, { 'create 201': r => r.status === 201 });
    if (c.status === 201) http.del(`${base}/api/travel-plans/${c.json('id')}`, null, { tags: { shard: 'new', name: 'DELETE plan' } });
  }
  sleep(0.1);
}
export function handleSummary(data) { return summary(data, 'rebalance'); }
