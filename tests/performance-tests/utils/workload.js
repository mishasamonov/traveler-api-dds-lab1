import http from 'k6/http';
import { check, sleep } from 'k6';
import exec from 'k6/execution';
import { ENDPOINTS, DEFAULT_HEADERS } from '../config/endpoints.js';
import { generateTravelPlan, generateLocation } from './data-generator.js';

// Fixed fixture size across runs. Never point these write tests at a production database.
export function request(method, url, body, expected, phase) {
  const r = http.request(method, url, body === null ? null : JSON.stringify(body), {
    headers: DEFAULT_HEADERS, timeout: '10s',
    tags: { phase, type: method === 'GET' ? 'read' : 'write',
      name: `${method} ${url.replace(/\/[0-9a-f-]{36}/g, '/:id')}` },
    responseCallback: http.expectedStatuses(expected),
  });
  check(r, { 'expected HTTP status': x => x.status === expected });
  return r;
}
function body(r, expected) { return r.status === expected ? r.json() : null; }
export function setup() {
  const health = request('GET', ENDPOINTS.HEALTH, null, 200, 'setup');
  if (health.status !== 200) throw new Error('API is not ready');
  const ids = [];
  for (let i = 0; i < 100; i++) {
    const plan = body(request('POST', ENDPOINTS.TRAVEL_PLANS, { ...generateTravelPlan(), title: `k6 fixture ${i}` }, 201, 'setup'), 201);
    if (!plan) throw new Error('Fixture creation failed');
    ids.push(plan.id);
    for (let j = 0; j < 3; j++) {
      if (request('POST', ENDPOINTS.LOCATIONS_FOR_PLAN(plan.id), generateLocation(), 201, 'setup').status !== 201)
        throw new Error('Fixture location creation failed');
    }
  }
  return { ids };
}
export function teardown(data) {
  for (const id of data.ids) request('DELETE', ENDPOINTS.TRAVEL_PLAN_BY_ID(id), null, 204, 'teardown');
}
export function phaseAt(timeline) {
  const elapsed = exec.instance.currentTestRunDuration / 1000;
  return (timeline.find(item => elapsed < item.until) || timeline[timeline.length - 1]).name;
}
export function journey(data, phase) {
  // Four browsing iterations and one private edit journey, each with a 1 s user pause.
  // Shared fixtures are read-only; writes use a separate plan to avoid artificial conflicts.
  const choice = (__VU + __ITER) % 5;
  if (choice < 3) {
    request('GET', ENDPOINTS.TRAVEL_PLAN_BY_ID(data.ids[(__VU + __ITER) % data.ids.length]), null, 200, phase);
  } else if (choice === 3) {
    request('GET', `${ENDPOINTS.TRAVEL_PLANS}?page=1&limit=20`, null, 200, phase);
  } else {
    const plan = body(request('POST', ENDPOINTS.TRAVEL_PLANS, generateTravelPlan(), 201, phase), 201);
    if (plan) {
      try {
        const location = body(request('POST', ENDPOINTS.LOCATIONS_FOR_PLAN(plan.id), generateLocation(), 201, phase), 201);
        if (location) request('PUT', ENDPOINTS.LOCATION_BY_ID(location.id), { notes: 'Tickets booked', version: location.version }, 200, phase);
        request('PUT', ENDPOINTS.TRAVEL_PLAN_BY_ID(plan.id), { budget: 2500, version: plan.version }, 200, phase);
        request('GET', ENDPOINTS.TRAVEL_PLAN_BY_ID(plan.id), null, 200, phase);
      } finally { request('DELETE', ENDPOINTS.TRAVEL_PLAN_BY_ID(plan.id), null, 204, phase); }
    }
  }
  sleep(Number(__ENV.THINK_TIME || 1));
}
export function thresholds(phases, stress = false) {
  const result = {
    'http_req_duration{type:read}': ['p(95)<500'],
    'http_req_duration{type:write}': ['p(95)<1000'],
    http_req_failed: ['rate<0.01'], checks: ['rate>0.99'],
  };
  // Phase-specific values let the report distinguish peak from setup and recovery.
  for (const phase of phases) {
    result[`http_req_duration{phase:${phase}}`] = ['p(95)<1000'];
    result[`http_req_failed{phase:${phase}}`] = ['rate<0.01'];
    result[`http_reqs{phase:${phase}}`] = ['count>0'];
  }
  return result;
}
