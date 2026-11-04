#!/usr/bin/env node
// Move one virtual node (db_0..db_f) between PostgreSQL services without stopping the API.
//   node tools/rebalance.js move db_3 postgres_03 [--drop-source]
//   node tools/rebalance.js status
// Algorithm (laboratory 6):
//   1. logical replication source -> target   2. wait for the initial sync
//   3. ACCESS EXCLUSIVE lock on the source     4. target: replica -> master
//   5. mapping file + shared registry          6. REVOKE on the old database
//   7. the API gets 42501, re-reads the mapping and retries on the new owner.
const fs = require('node:fs');
const { SHARDS, readMapping, writeMapping, connect, ident, ms, now, log, table } = require('./common');

const APP = ident(process.env.APP_USER);
const REPL = ident(process.env.REPL_USER);
const REGISTRY_REPLICAS = (process.env.REGISTRY_REPLICAS || '').split(',').filter(Boolean);
const sleep = t => new Promise(r => setTimeout(r, t));
const timings = [];
const step = async (name, fn) => {
  const t0 = now();
  log(`>> ${name}`);
  const result = await fn();
  timings.push({ step: name, ms: ms(t0) });
  return result;
};

const FINGERPRINT = `SELECT
  (SELECT count(*) FROM travel_plans)::int AS plans,
  (SELECT count(*) FROM locations)::int AS locations,
  (SELECT md5(coalesce(string_agg(row_to_json(t)::text, E'\\n' ORDER BY id), '')) FROM travel_plans t) AS plans_md5,
  (SELECT md5(coalesce(string_agg(row_to_json(t)::text, E'\\n' ORDER BY id), '')) FROM locations t) AS locations_md5`;

async function registryVersion(host) {
  const c = await connect(host, 'shard_registry');
  try { return Number((await c.query('SELECT version FROM registry_meta WHERE id = 1')).rows[0].version); }
  finally { await c.end(); }
}

async function move(database, target, options) {
  if (!/^db_[0-9a-f]$/.test(database)) throw new Error('Database must be db_0..db_f');
  const shard = database.slice(-1);
  const mapping = readMapping();
  const source = mapping.shards[shard].host;
  if (!/^postgres_0[0-3]$/.test(target)) throw new Error('Target must be postgres_00..postgres_03');
  if (source === target) throw new Error(`${database} already lives on ${target}`);
  const pub = ident(`move_${shard}_pub`), sub = ident(`move_${shard}_${target.slice(-2)}`);
  log(`move ${database}: ${source} -> ${target} (mapping v${mapping.version})`);

  const srcAdmin = await connect(source, 'postgres');
  const tgtAdmin = await connect(target, 'postgres');
  let src = await connect(source, database, { application_name: 'rebalance' });
  let tgt, lock, switched = false;
  try {
    await step('0. pre-checks', async () => {
      const exists = await tgtAdmin.query('SELECT 1 FROM pg_database WHERE datname = $1', [database]);
      if (exists.rowCount) throw new Error(`${database} already exists on ${target}`);
      const before = (await src.query(FINGERPRINT)).rows[0];
      log(`   source ${source}/${database}: ${before.plans} plans, ${before.locations} locations`);
    });

    await step('1. create target database and logical replication', async () => {
      await tgtAdmin.query(`CREATE DATABASE ${database}`);
      await tgtAdmin.query(`REVOKE ALL ON DATABASE ${database} FROM PUBLIC`);
      tgt = await connect(target, database, { application_name: 'rebalance' });
      await tgt.query(fs.readFileSync('db/migrations/001_schema.sql', 'utf8'));
      // Row-by-row apply cannot defer the unique order constraint the way the
      // API transaction does (SET CONSTRAINTS ... DEFERRED), so it is restored
      // after the final sync, inside the lock window.
      await tgt.query('ALTER TABLE locations DROP CONSTRAINT unique_plan_order');
      await tgt.query(`REVOKE CREATE ON SCHEMA public FROM PUBLIC; GRANT USAGE ON SCHEMA public TO ${APP}, ${REPL};
        GRANT SELECT ON ALL TABLES IN SCHEMA public TO ${REPL}`);
      await src.query(`DROP PUBLICATION IF EXISTS ${pub}`);
      await src.query(`CREATE PUBLICATION ${pub} FOR TABLE travel_plans, locations`);
      const conn = `host=${source} port=5432 dbname=${database} user=${REPL} password=${process.env.REPL_PASSWORD} application_name=${sub}`;
      await tgt.query(`CREATE SUBSCRIPTION ${sub} CONNECTION '${conn}' PUBLICATION ${pub} WITH (copy_data = true, slot_name = '${sub}')`);
      log(`   publication ${pub} on ${source}, subscription ${sub} on ${target}`);
    });

    await step('2. wait for initial copy and catch-up', async () => {
      for (let i = 0; ; i++) {
        const { rows } = await tgt.query(`SELECT count(*)::int AS tables, count(*) FILTER (WHERE srsubstate = 'r')::int AS ready
          FROM pg_subscription_rel r JOIN pg_subscription s ON s.oid = r.srsubid WHERE s.subname = $1`, [sub]);
        if (rows[0].tables === 2 && rows[0].ready === 2) break;
        if (i % 4 === 0) log(`   tables ready ${rows[0].ready}/2`);
        if (i > 600) throw new Error('Initial synchronization timeout');
        await sleep(250);
      }
      const lag = await srcAdmin.query(`SELECT pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)::bigint AS lag
        FROM pg_replication_slots WHERE slot_name = $1`, [sub]);
      const copy = (await tgt.query('SELECT (SELECT count(*) FROM travel_plans)::int AS plans, (SELECT count(*) FROM locations)::int AS locations')).rows[0];
      log(`   srsubstate=r for both tables; target has ${copy.plans} plans, ${copy.locations} locations; slot lag ${lag.rows[0]?.lag} bytes`);
    });

    let lockStart, lockedAt;
    await step('3. LOCK TABLE ... IN ACCESS EXCLUSIVE MODE on source', async () => {
      lock = await connect(source, database, { application_name: 'rebalance-lock' });
      await lock.query("SET lock_timeout = '5s'");
      await lock.query('BEGIN');
      lockStart = now();
      await lock.query('LOCK TABLE travel_plans, locations IN ACCESS EXCLUSIVE MODE');
      lockedAt = new Date().toISOString();
      const { rows: [{ lsn }] } = await lock.query('SELECT pg_current_wal_lsn() AS lsn');
      // Writes are frozen; wait until the subscriber confirmed everything up to now.
      for (let i = 0; ; i++) {
        const { rows } = await srcAdmin.query(`SELECT confirmed_flush_lsn >= $2::pg_lsn AS done, confirmed_flush_lsn
          FROM pg_replication_slots WHERE slot_name = $1`, [sub, lsn]);
        if (rows[0] && rows[0].done) { log(`   locked at ${lockedAt}; source LSN ${lsn}, confirmed ${rows[0].confirmed_flush_lsn}`); break; }
        if (i > 400) throw new Error('Subscriber did not reach the lock LSN');
        await sleep(25);
      }
      const a = (await lock.query(FINGERPRINT)).rows[0];
      const b = (await tgt.query(FINGERPRINT)).rows[0];
      log(`   source ${JSON.stringify(a)}`);
      log(`   target ${JSON.stringify(b)}`);
      if (JSON.stringify(a) !== JSON.stringify(b)) throw new Error('Source and target differ under the lock; aborting');
    });

    await step('4. promote target: drop subscription, restore constraint, grant API', async () => {
      await tgt.query(`ALTER SUBSCRIPTION ${sub} DISABLE`);
      await tgt.query(`ALTER SUBSCRIPTION ${sub} SET (slot_name = NONE)`);
      await tgt.query(`DROP SUBSCRIPTION ${sub}`);
      for (let i = 0; i < 200; i++) {
        const r = await srcAdmin.query('SELECT active FROM pg_replication_slots WHERE slot_name = $1', [sub]);
        if (!r.rowCount) break;
        if (!r.rows[0].active) { await srcAdmin.query('SELECT pg_drop_replication_slot($1)', [sub]); break; }
        await sleep(25);
      }
      await tgt.query(`ALTER TABLE locations ADD CONSTRAINT unique_plan_order UNIQUE (travel_plan_id, visit_order) DEFERRABLE INITIALLY IMMEDIATE`);
      await tgt.query(`GRANT CONNECT ON DATABASE ${database} TO ${APP}, ${REPL};
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO ${APP}`);
      await tgt.query(`COMMENT ON DATABASE ${database} IS 'TravelerAPI shard ${shard}, moved from ${source}'`);
    });

    let version;
    await step('5. update mapping file and shard registry', async () => {
      const reg = await connect('postgres_00', 'shard_registry');
      try {
        await reg.query('BEGIN');
        const current = Number((await reg.query('SELECT version FROM registry_meta WHERE id = 1 FOR UPDATE')).rows[0].version);
        version = Math.max(current, mapping.version) + 1;
        await reg.query('UPDATE shard_map SET host = $2, updated_at = now() WHERE shard = $1', [shard, target]);
        await reg.query('UPDATE registry_meta SET version = $1, updated_at = now() WHERE id = 1', [version]);
        await reg.query('INSERT INTO shard_moves(shard, from_host, to_host, version, lock_ms) VALUES ($1, $2, $3, $4, $5)',
          [shard, source, target, version, ms(lockStart)]);
        await reg.query('COMMIT');
      } finally { await reg.end(); }
      mapping.version = version;
      mapping.shards[shard] = { ...mapping.shards[shard], host: target };
      writeMapping(mapping);
      // The registry copies on the other services must see the new version
      // before the old database starts refusing requests.
      for (const host of REGISTRY_REPLICAS) {
        for (let i = 0; (await registryVersion(host)) < version; i++) {
          if (i > 400) throw new Error(`Registry replica ${host} is behind`);
          await sleep(25);
        }
      }
      log(`   mapping file and registry: version ${version}, shard ${shard} -> ${target}; replicas ${REGISTRY_REPLICAS.join(', ')} confirmed`);
    });

    let lockMs;
    await step('6. revoke API privileges on the old database and release the lock', async () => {
      await lock.query(`REVOKE ALL ON travel_plans, locations FROM ${APP}`);
      await lock.query(`REVOKE CONNECT ON DATABASE ${database} FROM ${APP}, PUBLIC`);
      await lock.query(`COMMENT ON DATABASE ${database} IS 'MOVED to ${target} (mapping v${version})'`);
      await lock.query(`DROP PUBLICATION ${pub}`);
      await lock.query('COMMIT');
      lockMs = ms(lockStart);
      switched = true;
      log(`   lock held ${lockMs} ms; waiting API queries now get 42501 and re-read the mapping`);
    });

    if (options.dropSource) await step('7. drop the old database', async () => {
      // WITH (FORCE) terminates every session of the old database, including
      // the tool's own ones, so they are closed first.
      await lock.end(); lock = null;
      await src.end(); src = null;
      await srcAdmin.query(`DROP DATABASE ${database} WITH (FORCE)`);
      log(`   ${source}/${database} dropped; API pools to it are closed by the server`);
    });
    console.log(table(timings, ['step', 'ms']));
    log(`DONE ${database}: ${source} -> ${target}, mapping v${version}, write freeze ${lockMs} ms`);
  } catch (error) {
    if (lock) await lock.query('ROLLBACK').catch(() => {});
    log(switched
      ? `FAILED after the switch: ${error.message}. ${target} already serves the shard; only the cleanup of ${source}/${database} is left.`
      : `FAILED: ${error.message}. The source keeps serving the shard; target ${target}/${database} must be dropped before a retry.`);
    throw error;
  } finally {
    for (const c of [lock, tgt, src, srcAdmin, tgtAdmin]) if (c) await c.end().catch(() => {});
  }
}

async function status() {
  const mapping = readMapping();
  const rows = [];
  for (const host of ['postgres_00', 'postgres_01', 'postgres_02', 'postgres_03']) {
    const c = await connect(host, 'postgres');
    const dbs = (await c.query(`SELECT datname, has_database_privilege($1, datname, 'CONNECT') AS api,
      pg_size_pretty(pg_database_size(datname)) AS size FROM pg_database WHERE datname ~ '^db_' ORDER BY datname`, [APP])).rows;
    await c.end();
    const reg = await registryVersion(host);
    rows.push({ server: host, registry: `v${reg}`, databases: dbs.map(d => d.datname + (d.api ? '' : '(revoked)')).join(' '),
      mapped: SHARDS.filter(s => mapping.shards[s].host === host).map(s => 'db_' + s).join(' ') });
  }
  console.log(`mapping file v${mapping.version}`);
  console.log(table(rows, ['server', 'registry', 'mapped', 'databases']));
}

const [command, ...rest] = process.argv.slice(2);
const run = command === 'move' ? move(rest[0], rest[1], { dropSource: rest.includes('--drop-source') })
  : command === 'status' ? status() : Promise.reject(new Error('Usage: rebalance.js move <db_x> <postgres_0N> [--drop-source] | status'));
run.catch(error => { console.error(error.message); process.exitCode = 1; });
