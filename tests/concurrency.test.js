const { test } = require('node:test');
const assert = require('node:assert/strict');

const base = 'http://127.0.0.1:4567';
async function request(method, path, body) {
  const response = await fetch(`${base}${path}`, {
    method,
    headers: body ? { 'content-type': 'application/json' } : {},
    body: body ? JSON.stringify(body) : undefined,
  });
  return { status: response.status, data: response.status === 204 ? null : await response.json() };
}

test('two concurrent plan edits with the same version: one update, one conflict', async t => {
  const created = await request('POST', '/api/travel-plans', { title: 'Parallel plan', budget: 2000 });
  assert.equal(created.status, 201);
  const id = created.data.id;
  t.after(() => request('DELETE', `/api/travel-plans/${id}`));

  const results = await Promise.all([
    request('PUT', `/api/travel-plans/${id}`, { budget: 2500, version: 1 }),
    request('PUT', `/api/travel-plans/${id}`, { title: 'New title', version: 1 }),
  ]);
  assert.deepEqual(results.map(x => x.status).sort(), [200, 409]);
  const read = await request('GET', `/api/travel-plans/${id}`);
  assert.equal(read.data.version, 2);
  assert.equal(results.find(x => x.status === 409).data.current_version, 2);
});

test('concurrent location additions get unique orders and reorder shifts neighbors', async t => {
  const created = await request('POST', '/api/travel-plans', { title: 'Parallel locations' });
  assert.equal(created.status, 201);
  const id = created.data.id;
  t.after(() => request('DELETE', `/api/travel-plans/${id}`));

  const result = await Promise.all(Array.from({ length: 12 }, (_, i) =>
    request('POST', `/api/travel-plans/${id}/locations`, { name: `Location ${i + 1}` })));
  assert.ok(result.every(x => x.status === 201), JSON.stringify(result.filter(x => x.status !== 201)));
  assert.deepEqual(result.map(x => x.data.visit_order).sort((a, b) => a - b), Array.from({ length: 12 }, (_, i) => i + 1));

  const last = result.find(x => x.data.visit_order === 12).data;
  const moved = await request('PUT', `/api/locations/${last.id}`, { visit_order: 1, version: last.version });
  assert.equal(moved.status, 200, JSON.stringify(moved.data));
  const read = await request('GET', `/api/travel-plans/${id}`);
  assert.equal(read.data.locations[0].id, last.id);
  assert.deepEqual(read.data.locations.map(x => x.visit_order), Array.from({ length: 12 }, (_, i) => i + 1));
  assert.equal(read.data.locations[1].version, 2, 'shifted neighbor must receive a new version');
});

test('two concurrent location edits reject a stale version, then allow safe retry', async t => {
  const plan = await request('POST', '/api/travel-plans', { title: 'Location version' });
  assert.equal(plan.status, 201);
  const id = plan.data.id;
  t.after(() => request('DELETE', `/api/travel-plans/${id}`));
  const created = await request('POST', `/api/travel-plans/${id}/locations`, { name: 'Paris', notes: 'Book tickets', budget: 50 });
  assert.equal(created.status, 201);
  const locId = created.data.id;

  const results = await Promise.all([
    request('PUT', `/api/locations/${locId}`, { budget: 75, version: 1 }),
    request('PUT', `/api/locations/${locId}`, { notes: 'Tickets booked!', version: 1 }),
  ]);
  assert.deepEqual(results.map(x => x.status).sort(), [200, 409]);
  assert.equal(results.find(x => x.status === 409).data.current_version, 2);
  const fresh = (await request('GET', `/api/travel-plans/${id}`)).data.locations[0];
  assert.equal(fresh.version, 2);
  const retry = await request('PUT', `/api/locations/${locId}`, {
    ...(fresh.budget === 75 ? { notes: 'Tickets booked!' } : { budget: 75 }), version: fresh.version,
  });
  assert.equal(retry.status, 200);
  assert.equal(retry.data.version, 3);
  assert.equal(retry.data.budget, 75);
  assert.equal(retry.data.notes, 'Tickets booked!');
});
