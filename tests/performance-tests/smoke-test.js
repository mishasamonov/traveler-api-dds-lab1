// CRUD smoke journey adapted from instructor/smoke-test.original.js.
import { check, sleep } from 'k6';
import { ENDPOINTS as E } from './config/endpoints.js';
import { request, json } from './utils/api-client.js';
import { generateTravelPlan, generateLocation } from './utils/data-generator.js';
import { summary } from './utils/summary.js';
export const options = {
  scenarios: { default: { executor: 'ramping-vus', startVUs: 0,
    stages: [{ duration: '5s', target: 2 }, { duration: '10s', target: 5 }, { duration: '5s', target: 0 }],
    gracefulRampDown: '30s', gracefulStop: '30s' } },
  summaryTrendStats: ['avg', 'min', 'med', 'max', 'p(90)', 'p(95)', 'p(99)'],
  thresholds: { http_req_failed: ['rate==0'], http_req_duration: ['p(95)<500'], checks: ['rate==1'], api_errors: ['rate==0'] },
};
export default function () {
  request('GET', E.HEALTH, null);
  request('GET', E.TRAVEL_PLANS, null);
  const p = json(request('POST', E.TRAVEL_PLANS, generateTravelPlan(), 201));
  if (!p?.id) return;
  try {
    request('GET', E.TRAVEL_PLAN_BY_ID(p.id), null);
    const loc = json(request('POST', E.LOCATIONS_FOR_PLAN(p.id), generateLocation(), 201));
    if (!loc?.id) return;
    const updated = json(request('PUT', E.LOCATION_BY_ID(loc.id), { version: loc.version, notes: 'k6 edited location' }));
    check(updated, { 'location version increments': x => x?.version === loc.version + 1 });
    request('PUT', E.LOCATION_BY_ID(loc.id), { version: loc.version, notes: 'stale update' }, 409);
    const fresh = json(request('GET', E.TRAVEL_PLAN_BY_ID(p.id), null));
    check(fresh, { 'stale location update did not overwrite data': x => x?.locations?.[0]?.notes === 'k6 edited location' });
    if (updated) request('PUT', E.LOCATION_BY_ID(loc.id), { version: updated.version, budget: 42 });
    const plan2 = json(request('PUT', E.TRAVEL_PLAN_BY_ID(p.id), { version: p.version, title: 'k6 updated plan' }));
    check(plan2, { 'plan version increments': x => x?.version === p.version + 1 });
    request('DELETE', E.LOCATION_BY_ID(loc.id), null, 204);
  } finally {
    request('DELETE', E.TRAVEL_PLAN_BY_ID(p.id), null, 204);
    request('GET', E.TRAVEL_PLAN_BY_ID(p.id), null, 404);
  }
  sleep(0.5);
}
export function handleSummary(data) { return summary(data, 'smoke'); }
