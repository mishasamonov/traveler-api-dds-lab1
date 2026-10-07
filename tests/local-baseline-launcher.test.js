'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const net = require('node:net');
const { quoteIdentifier, quoteLiteral, acceptExit, summarize, requireFreePort, prepareDatabase } =
  require('../scripts/run-local-baseline');

test('SQL quoting does not concatenate an unescaped identifier or password', () => {
  assert.equal(quoteIdentifier('a"b'), '"a""b"');
  assert.equal(quoteLiteral("x'y"), "'x''y'");
});

test('only stress and spike may cross k6 performance thresholds', () => {
  for (const name of ['smoke', 'load', 'stress', 'spike', 'endurance']) {
    assert.equal(acceptExit(name, 0), true);
    assert.equal(acceptExit(name, 99), ['stress', 'spike'].includes(name));
    assert.equal(acceptExit(name, 1), false);
    assert.equal(acceptExit(name, null), false);
  }
});

test('aggregation uses measured JSON values and does not invent missing scenarios', t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'lab2-launcher-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  fs.writeFileSync(path.join(directory, 'smoke-summary.json'), JSON.stringify({
    metrics: { http_reqs: { values: { count: 15 } }, vus_max: { values: { max: 5 } },
      http_req_duration: { values: { avg: 2.5, 'p(95)': 4.25 } },
      http_req_failed: { values: { rate: 0.02 } }, checks: { values: { rate: 0.98 } } },
    state: { testRunDurationMs: 23000 },
  }));
  const rows = summarize(directory, ['smoke']);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].p95Ms, 4.25);
  assert.equal(rows[0].durationMs, 23000);
  assert.equal(rows[0].httpFailureRate, 0.02);
  const csv = fs.readFileSync(path.join(directory, 'local-results.csv'), 'utf8');
  assert.match(csv, /smoke,15,5,2.5,4.25,2,98,23000/);
  assert.doesNotMatch(csv, /endurance/);
  assert.equal(JSON.parse(fs.readFileSync(path.join(directory, 'local-results.json')))[0].checksRate, 0.98);
});

test('an existing API is not stopped or silently reused', async t => {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  await assert.rejects(requireFreePort(server.address().port), /зайнятий/);
  assert.equal(server.listening, true);
});

test('a free local port passes the non-mutating preflight', async () => {
  await requireFreePort(0);
});

test('new dedicated DB saves only its generated credential, not the admin password', async t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'lab2-db-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const file = path.join(directory, 'database.json');
  const queries = [];
  const inputs = ['', '', 'TEST-ADMIN-SECRET'];
  class FakeClient {
    constructor(config) { assert.equal(config.password, 'TEST-ADMIN-SECRET'); }
    async connect() {}
    async query(sql) {
      queries.push(sql);
      if (sql === 'SHOW server_version_num') return { rows: [{ server_version_num: '160015' }] };
    }
    async end() {}
  }
  const url = await prepareDatabase(async () => inputs.shift(), file, FakeClient);
  assert.equal(new URL(url).hostname, '127.0.0.1');
  assert.match(new URL(url).pathname, /^\/traveler_lab2_[a-f0-9]{12}$/);
  assert.match(queries[1], /^CREATE ROLE "traveler_lab2_[a-f0-9]{12}" LOGIN PASSWORD '[a-f0-9]{48}'$/);
  assert.match(queries[2], /^CREATE DATABASE "traveler_lab2_[a-f0-9]{12}" OWNER "traveler_lab2_[a-f0-9]{12}"$/);
  assert.doesNotMatch(fs.readFileSync(file, 'utf8'), /TEST-ADMIN-SECRET/);
  assert.equal(await prepareDatabase(() => assert.fail('must not ask again'), file, FakeClient), url);
});

test('remote DB configuration is refused before any connection or change', async t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'lab2-config-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const file = path.join(directory, 'database.json');
  fs.writeFileSync(file, JSON.stringify({ databaseUrl: 'postgres://user:pass@example.com/traveler_lab2_abcdef123456' }));
  await assert.rejects(prepareDatabase(() => assert.fail('must not prompt'), file,
    class { constructor() { assert.fail('must not connect'); } }), /сторонню БД/);
});

test('failed database creation cleans up only the brand-new role', async t => {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'lab2-cleanup-test-'));
  t.after(() => fs.rmSync(directory, { recursive: true, force: true }));
  const queries = [];
  class FakeClient {
    async connect() {}
    async query(sql) {
      queries.push(sql);
      if (sql === 'SHOW server_version_num') return { rows: [{ server_version_num: '160015' }] };
      if (sql.startsWith('CREATE DATABASE')) throw new Error('test creation failed');
    }
    async end() {}
  }
  const file = path.join(directory, 'database.json');
  await assert.rejects(prepareDatabase(async () => '', file, FakeClient), /test creation failed/);
  const createdName = queries[1].match(/^CREATE ROLE ("[^"]+")/)[1];
  assert.equal(queries[3], 'DROP ROLE ' + createdName);
  assert.equal(fs.existsSync(file), false);
});
