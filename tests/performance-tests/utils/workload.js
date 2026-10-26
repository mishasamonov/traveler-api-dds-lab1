import { sleep, fail } from 'k6';
import exec from 'k6/execution';
import { SharedArray } from 'k6/data';
import { ENDPOINTS as E } from '../config/endpoints.js';
import { request, json } from './api-client.js';
// Seed lives outside the measured interval. Each VU owns one existing plan.
const seed = new SharedArray('seed', () => JSON.parse(open('../seed.json')));
let current;
export const profiles = {
  load: [[10,25,'ramp25'],[30,25,'load25'],[10,50,'ramp50'],[30,50,'load50'],[10,100,'ramp100'],[30,100,'load100'],[10,200,'ramp200'],[30,200,'load200'],[10,0,'cooldown']],
  stress: [[10,200,'ramp200'],[45,200,'stress200'],[10,500,'ramp500'],[45,500,'stress500'],[10,1000,'ramp1000'],[45,1000,'stress1000'],[10,2000,'ramp2000'],[45,2000,'stress2000'],[10,20,'down'],[60,20,'recovery'],[10,0,'cooldown']],
  spike: [[5,20,'warmup'],[30,20,'before'],[1,1000,'rise'],[30,1000,'spike'],[1,20,'fall'],[60,20,'recovery'],[5,0,'cooldown']],
  endurance: [[30,25,'warmup'],[1800,25,'steady'],[30,0,'cooldown']],
};
export function optionsFor(name) {
  return {
    scenarios: { default: {
      executor: 'ramping-vus', startVUs: 0,
      stages: profiles[name].map(([duration,target]) => ({ duration: `${duration}s`, target })),
      gracefulRampDown: '30s', gracefulStop: '30s',
    } },
    summaryTrendStats: ['avg','min','med','max','p(90)','p(95)','p(99)'],
    systemTags: ['status','method','name','scenario','expected_response'],
    thresholds: {
      http_req_failed: ['rate<0.01'], http_req_duration: ['p(95)<500'], checks: ['rate>0.99'],
      ...(name === 'stress' || name === 'spike' ? { 'http_req_duration{phase:recovery}': ['p(95)<500'] } : {}),
    },
  };
}
export function setup() {
  const r = request('GET', E.HEALTH, null, 200, { phase: 'setup' });
  if (r.status !== 200) fail('API must be healthy before measurement');
  if (seed.length < 2000) fail('Run scripts/seed-performance.cjs first (2000 plans required)');
}
function phase(name) {
  let until = 0;
  const elapsed = (Date.now() - exec.scenario.startTime) / 1000;
  for (const [seconds,,label] of profiles[name]) { until += seconds; if (elapsed < until) return label; }
  return 'drain';
}
export function journey(name) {
  const tags = { phase: phase(name) };
  const owned = seed[(__VU - 1) % seed.length];
  if (!current) current = json(request('GET', E.TRAVEL_PLAN_BY_ID(owned.id), null, 200, tags));
  if (!current) { sleep(0.5); return; }
  // Eight reads and two writes per normal iteration: list, detail, update plan/location.
  for (let i = 0; i < 4; i++) {
    request('GET', `${E.TRAVEL_PLANS}?page=${1 + (__VU % 10)}&limit=20`, null, 200, tags);
    const fresh = json(request('GET', E.TRAVEL_PLAN_BY_ID(current.id), null, 200, tags));
    if (fresh) current = fresh;
    sleep(0.1);
  }
  const updated = json(request('PUT', E.TRAVEL_PLAN_BY_ID(current.id), { version: current.version, budget: (__ITER % 100) + 100 }, 200, tags));
  if (updated?.version) current.version = updated.version;
  const location = current.locations?.[0];
  if (location) {
    const result = json(request('PUT', E.LOCATION_BY_ID(location.id), { version: location.version, notes: `iteration ${__ITER}` }, 200, tags));
    if (result?.version) location.version = result.version;
  }
  // Once per ten journeys, exercise create, location insert, and cascade delete.
  if (__ITER % 10 === 0) {
    const p = json(request('POST', E.TRAVEL_PLANS, { title: `k6 temporary ${__VU} ${__ITER}` }, 201, tags));
    if (p?.id) {
      request('POST', E.LOCATIONS_FOR_PLAN(p.id), { name: 'k6 temporary location' }, 201, tags);
      request('DELETE', E.TRAVEL_PLAN_BY_ID(p.id), null, 204, tags);
    }
  }
  sleep(0.1);
}
