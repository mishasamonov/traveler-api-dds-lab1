#!/usr/bin/env node
'use strict';

// Native local run only: no Docker, no cloud service and no change to Lab1 data.
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const net = require('node:net');
const crypto = require('node:crypto');
const readline = require('node:readline');
const { spawn, spawnSync } = require('node:child_process');
const { once } = require('node:events');

const ROOT = path.resolve(__dirname, '..');
const PRIVATE_DIR = path.join(ROOT, '.lab2-local');
const CONFIG_FILE = path.join(PRIVATE_DIR, 'database.json');
const SCENARIOS = ['smoke', 'load', 'stress', 'spike', 'endurance'];

function locateK6(env = process.env) {
  const candidates = [env.K6_BIN, path.join(ROOT, 'tools', 'k6.exe'),
    path.join(ROOT, 'tools', 'k6'), 'k6'].filter(Boolean);
  for (const file of candidates) {
    const result = spawnSync(file, ['version'], { encoding: 'utf8', env, windowsHide: true });
    if (!result.error && result.status === 0) return { file, version: result.stdout.trim() };
  }
  throw new Error('Не знайдено k6. Поклади k6.exe у tools/ або встанови k6 та відкрий термінал знову.');
}

function ask(question, secret = false) {
  if (!process.stdin.isTTY) throw new Error('Запусти команду у звичайному інтерактивному терміналі.');
  if (!secret) {
    const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
    return new Promise(resolve => rl.question(question, answer => { rl.close(); resolve(answer.trim()); }));
  }
  // The admin password is not echoed, logged, passed as an argument or saved.
  process.stdout.write(question);
  readline.emitKeypressEvents(process.stdin);
  const previousRaw = process.stdin.isRaw;
  process.stdin.setRawMode(true);
  process.stdin.resume();
  return new Promise((resolve, reject) => {
    let value = '';
    function finish(error) {
      process.stdin.off('keypress', keypress);
      process.stdin.setRawMode(Boolean(previousRaw));
      process.stdin.pause();
      process.stdout.write('\n');
      if (error) reject(error); else resolve(value);
    }
    function keypress(text, key = {}) {
      if (key.ctrl && key.name === 'c') return finish(new Error('Запуск скасовано.'));
      if (key.name === 'return' || key.name === 'enter') return finish();
      if (key.name === 'backspace') { value = value.slice(0, -1); return; }
      if (!key.ctrl && !key.meta && text && !/[\x00-\x1f\x7f]/.test(text)) value += text;
    }
    process.stdin.on('keypress', keypress);
  });
}

function quoteIdentifier(value) { return '"' + value.replaceAll('"', '""') + '"'; }
function quoteLiteral(value) { return "'" + value.replaceAll("'", "''") + "'"; }

async function prepareDatabase(prompt = ask, configFile = CONFIG_FILE, Client = require('pg').Client) {
  if (fs.existsSync(configFile)) {
    const config = JSON.parse(fs.readFileSync(configFile, 'utf8'));
    const url = new URL(config.databaseUrl);
    if (url.hostname !== '127.0.0.1' || !/^\/traveler_lab2_[a-f0-9]{12}$/.test(url.pathname)) {
      throw new Error('Некоректна локальна конфігурація. Не використовую сторонню БД.');
    }
    return config.databaseUrl;
  }
  console.log('Перший запуск: буде створено НОВУ окрему БД traveler_lab2_…; дані ЛР1 не змінюються.');
  const port = Number((await prompt('Порт PostgreSQL [5432]: ')) || 5432);
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Некоректний порт PostgreSQL.');
  const user = (await prompt('Адміністратор PostgreSQL [postgres]: ')) || 'postgres';
  const password = await prompt('Пароль цього користувача (введення приховане): ', true);
  const admin = new Client({ host: '127.0.0.1', port, user, password, database: 'postgres',
    connectionTimeoutMillis: 5000 });
  const name = 'traveler_lab2_' + crypto.randomBytes(6).toString('hex');
  const dbPassword = crypto.randomBytes(24).toString('hex');
  try {
    await admin.connect();
    const { rows } = await admin.query('SHOW server_version_num');
    if (Math.floor(Number(rows[0].server_version_num) / 10000) !== 16) {
      throw new Error('Для однакового baseline потрібен PostgreSQL 16. Поточний сервер має іншу версію.');
    }
    await admin.query(`CREATE ROLE ${quoteIdentifier(name)} LOGIN PASSWORD ${quoteLiteral(dbPassword)}`);
    try {
      await admin.query(`CREATE DATABASE ${quoteIdentifier(name)} OWNER ${quoteIdentifier(name)}`);
    } catch (error) {
      // Remove only the role created by this invocation, never an existing role/database.
      await admin.query(`DROP ROLE ${quoteIdentifier(name)}`).catch(() => {});
      throw error;
    }
    const databaseUrl = `postgres://${name}:${dbPassword}@127.0.0.1:${port}/${name}`;
    fs.mkdirSync(path.dirname(configFile), { recursive: true, mode: 0o700 });
    fs.writeFileSync(configFile, JSON.stringify({ databaseUrl }, null, 2), { flag: 'wx', mode: 0o600 });
    return databaseUrl;
  } finally {
    await admin.end().catch(() => {});
  }
}

async function checkDatabase(databaseUrl) {
  const { Client } = require('pg');
  const client = new Client({ connectionString: databaseUrl, connectionTimeoutMillis: 5000 });
  try {
    await client.connect();
    const { rows } = await client.query('SELECT version() AS version, current_setting(\'server_version_num\') AS number');
    if (Math.floor(Number(rows[0].number) / 10000) !== 16) throw new Error('Потрібен PostgreSQL 16.');
    return rows[0].version;
  } finally { await client.end().catch(() => {}); }
}

async function requireFreePort(port) {
  const server = net.createServer();
  await new Promise((resolve, reject) => {
    server.once('error', () => reject(new Error(`Порт ${port} зайнятий. Зупини попередній API і повтори запуск.`)));
    server.listen(port, '127.0.0.1', resolve);
  });
  await new Promise(resolve => server.close(resolve));
}

function startLogged(command, args, env, logFile) {
  const log = fs.createWriteStream(logFile, { flags: 'wx' });
  const child = spawn(command, args, { cwd: ROOT, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] });
  child.stdout.on('data', chunk => { process.stdout.write(chunk); log.write(chunk); });
  child.stderr.on('data', chunk => { process.stderr.write(chunk); log.write(chunk); });
  const done = new Promise((resolve, reject) => {
    child.once('error', error => { log.end(); reject(error); });
    child.once('close', (code, signal) => {
      log.end(() => resolve({ code, signal }));
    });
  });
  return { child, done };
}

async function waitForApi(child, url) {
  for (let attempt = 0; attempt < 60; attempt++) {
    if (child.exitCode !== null) throw new Error('API завершився до початку тестів. Дивись api.log.');
    try {
      const response = await fetch(url + '/health', { signal: AbortSignal.timeout(1000) });
      const body = await response.json();
      if (response.ok && body.status === 'ok' && body.database === 'connected') return;
    } catch { /* Allow startup time; do not contact a remote endpoint. */ }
    await new Promise(resolve => setTimeout(resolve, 250));
  }
  throw new Error('API не готовий. Дивись api.log у каталозі результатів.');
}

function acceptExit(name, code) {
  return code === 0 || (code === 99 && ['stress', 'spike'].includes(name));
}

function summarize(directory, names) {
  const rows = names.map(name => {
    const data = JSON.parse(fs.readFileSync(path.join(directory, `${name}-summary.json`), 'utf8'));
    const m = data.metrics;
    return { scenario: name, requests: m.http_reqs.values.count, maxVU: m.vus_max.values.max,
      averageMs: m.http_req_duration.values.avg, p95Ms: m.http_req_duration.values['p(95)'],
      httpFailureRate: m.http_req_failed.values.rate, checksRate: m.checks.values.rate,
      durationMs: data.state?.testRunDurationMs };
  });
  fs.writeFileSync(path.join(directory, 'local-results.json'), JSON.stringify(rows, null, 2));
  const lines = ['scenario,requests,max_vu,avg_ms,p95_ms,http_failed_percent,checks_percent,duration_ms',
    ...rows.map(r => [r.scenario, r.requests, r.maxVU, r.averageMs, r.p95Ms,
      r.httpFailureRate * 100, r.checksRate * 100, r.durationMs].join(','))];
  fs.writeFileSync(path.join(directory, 'local-results.csv'), lines.join('\r\n') + '\r\n');
  console.table(rows.map(r => ({ Тест: r.scenario, Запитів: r.requests, VU: r.maxVU,
    'avg, мс': r.averageMs.toFixed(2), 'p95, мс': r.p95Ms.toFixed(2),
    'Помилок, %': (r.httpFailureRate * 100).toFixed(3) })));
  return rows;
}

async function stopOwnedProcess(child) {
  if (!child || child.exitCode !== null || child.signalCode !== null) return;
  const closed = once(child, 'close');
  child.kill('SIGTERM');
  const timer = setTimeout(() => child.kill('SIGKILL'), 3000);
  await closed;
  clearTimeout(timer);
}

async function main(args = process.argv.slice(2)) {
  if (args.some(arg => !['--check', '--smoke'].includes(arg)) || args.length > 1) {
    throw new Error('Варіанти: node scripts/run-local-baseline.js [--check | --smoke]');
  }
  process.chdir(ROOT);
  if (Number(process.versions.node.split('.')[0]) !== 24) throw new Error('Встанови Node.js 24 LTS.');
  try { require.resolve('pg'); } catch { throw new Error('Спочатку виконай npm.cmd ci (Windows) або npm ci.'); }
  const k6 = locateK6();
  console.log(`Node ${process.version}; ${k6.version}`);
  if (!/\bk6 v1\.3\.0\b/.test(k6.version)) console.warn('У CI використано k6 1.3.0; інша версія буде записана окремо.');
  if (args.includes('--check')) {
    console.log('Node та k6 доступні. БД/фізичний ПК ще не перевірено; вимірювання НЕ виконувалися.');
    return;
  }
  if (process.env.WSL_DISTRO_NAME || process.env.GITHUB_ACTIONS || fs.existsSync('/.dockerenv')) {
    throw new Error('Цей запуск не є baseline фізичного ПК. Запусти нативно у Windows/Linux/macOS, без WSL/Docker/CI.');
  }
  const confirmation = await ask('API, k6 та PostgreSQL запущені на одному фізичному ПК без VM/Docker/WSL? [так/ні]: ');
  if (!['так', 'yes', 'y'].includes(confirmation.toLowerCase())) throw new Error('Baseline не розпочато.');
  await requireFreePort(4567);
  const databaseUrl = await prepareDatabase();
  const postgresVersion = await checkDatabase(databaseUrl);
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const directory = path.join(ROOT, 'tests', 'performance-tests', 'reports', 'local-' + stamp);
  fs.mkdirSync(directory, { recursive: true });
  const apiUrl = 'http://127.0.0.1:4567';
  const env = { ...process.env, DATABASE_URL: databaseUrl, PG_POOL_MAX: '20', PORT: '4567', API_URL: apiUrl };
  // Ignore unrelated global k6 overrides: they could change duration/VUs or send output remotely.
  for (const key of Object.keys(env)) if (key.startsWith('K6_')) delete env[key];
  const k6Config = path.join(directory, 'k6-config.json');
  fs.writeFileSync(k6Config, '{}\n');
  const cpus = os.cpus();
  fs.writeFileSync(path.join(directory, 'environment.json'), JSON.stringify({
    recordedAt: new Date().toISOString(), os: { platform: os.platform(), release: os.release(), arch: os.arch() },
    cpuModel: cpus[0]?.model, logicalCPUs: cpus.length, totalMemoryBytes: os.totalmem(),
    nodeVersion: process.version, k6Version: k6.version, postgresVersion, poolSize: 20,
    isolationLevel: 'READ COMMITTED',
    physicalPc: 'Підтверджено користувачем; це не автоматичний доказ відсутності VM.',
  }, null, 2));
  console.log('Результати: ' + directory);
  const init = startLogged(process.execPath, [path.join(ROOT, 'scripts', 'init-db.js')], env,
    path.join(directory, 'db-init.log'));
  if ((await init.done).code !== 0) throw new Error('Не вдалося застосувати схему до окремої БД ЛР2.');
  const api = startLogged(process.execPath, [path.join(ROOT, 'scripts', 'local-baseline-server.js')], env,
    path.join(directory, 'api.log'));
  let activeTest;
  let interrupted = false;
  let failure;
  const completed = [];
  const interrupt = () => { interrupted = true; activeTest?.kill('SIGINT'); };
  process.on('SIGINT', interrupt);
  process.on('SIGTERM', interrupt);
  try {
    await waitForApi(api.child, apiUrl);
    console.log(args.includes('--smoke') ? 'Лише Smoke: приблизно 30 с.' :
      'Повний цикл: приблизно 40 хв. Endurance триває 30 хв; не закривай термінал і не присипляй ПК.');
    for (const name of args.includes('--smoke') ? ['smoke'] : SCENARIOS) {
      if (interrupted) throw new Error('Запуск перервано. Збережені часткові результати не є повним baseline.');
      console.log(`\n=== ${name.toUpperCase()} ===`);
      const test = startLogged(k6.file, ['run', '--config', k6Config, '--no-usage-report', '--no-color', '--quiet',
        `tests/performance-tests/${name}-test.js`],
        { ...env, TEST_NAME: name, REPORT_DIR: directory, K6_WEB_DASHBOARD: 'true',
          K6_WEB_DASHBOARD_PORT: '-1', K6_WEB_DASHBOARD_PERIOD: '2s',
          K6_WEB_DASHBOARD_EXPORT: path.join(directory, `${name}-dashboard.html`) },
        path.join(directory, `${name}.log`));
      activeTest = test.child;
      const { code, signal } = await test.done;
      activeTest = undefined;
      fs.appendFileSync(path.join(directory, 'exit-codes.txt'), `${name} ${code ?? signal}\n`);
      if (fs.existsSync(path.join(directory, `${name}-summary.json`))) completed.push(name);
      if (interrupted || signal) throw new Error('Тест перервано; цикл не завершено.');
      if (!acceptExit(name, code)) {
        failure = new Error(`${name}: код ${code}. Дивись ${name}.log. Пороги не пройдено або є помилка запуску.`);
        if (name === 'smoke' || code !== 99) throw failure;
      }
    }
  } finally {
    await stopOwnedProcess(activeTest);
    await stopOwnedProcess(api.child);
    await api.done;
    process.off('SIGINT', interrupt);
    process.off('SIGTERM', interrupt);
    if (completed.length) summarize(directory, completed);
  }
  if (failure) throw failure;
  const expectedCount = args.includes('--smoke') ? 1 : SCENARIOS.length;
  if (completed.length !== expectedCount) throw new Error('Не всі JSON-звіти збережено. Цикл не є повним baseline.');
  if (args.includes('--smoke')) console.log('Smoke завершено. Для звіту ще потрібен повний цикл без --smoke.');
  else console.log('П’ять тестів завершено. Надішли каталог local-… для оновлення звіту фактичними локальними числами.');
  console.log('БД ЛР2 залишена для повторного запуску; пароль адміністратора ніде не збережено.');
}

module.exports = { locateK6, quoteIdentifier, quoteLiteral, acceptExit, summarize, requireFreePort, prepareDatabase };
if (require.main === module) main().catch(error => {
  // Never print a connection URL or a stack that could contain a password.
  console.error('ЛР2: ' + String(error.message).replace(/postgres(?:ql)?:\/\/\S+/gi, '[приховано]'));
  process.exitCode = 1;
});
