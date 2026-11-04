#!/usr/bin/env node
// Apply one DDL/DML script to all 16 shard databases atomically.
//   node tools/shard-exec.js <file.sql> [--dry-run] [--mapping file]
//   node tools/shard-exec.js --recover <gid-prefix> commit|rollback
// Phase 1: BEGIN + whole file on every shard (in parallel).
// Phase 2: only if all 16 succeeded -> PREPARE TRANSACTION on every shard.
// Phase 3: only if all 16 prepared  -> COMMIT PREPARED on every shard.
// Any error before phase 3 -> ROLLBACK / ROLLBACK PREPARED everywhere.
const fs = require('node:fs');
const crypto = require('node:crypto');
const { SHARDS, readMapping, connect, ms, now, log, table } = require('./common');

function parse(argv) {
  const args = { dryRun: false, mapping: undefined };
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--dry-run') args.dryRun = true;
    else if (argv[i] === '--show-prepared') args.showPrepared = true;
    else if (argv[i] === '--mapping') args.mapping = argv[++i];
    else if (argv[i] === '--recover') { args.recover = argv[++i]; args.decision = argv[++i]; }
    else args.file = argv[i];
  }
  return args;
}

// The tool owns the transaction. Scripts with their own transaction control or
// statements that cannot run inside a transaction block are refused up front.
function check(sql) {
  const code = sql.replace(/--[^\n]*/g, '').replace(/\/\*[\s\S]*?\*\//g, '').replace(/'(?:[^']|'')*'/g, "''");
  const forbidden = /\b(BEGIN|COMMIT|ROLLBACK|START\s+TRANSACTION|SAVEPOINT|PREPARE\s+TRANSACTION|VACUUM|CONCURRENTLY|CREATE\s+DATABASE|DROP\s+DATABASE|ALTER\s+SYSTEM)\b/i;
  const plpgsqlBodies = code.replace(/\$([a-z_]*)\$[\s\S]*?\$\1\$/gi, '');
  const match = plpgsqlBodies.match(forbidden);
  if (match) throw new Error(`Statement "${match[0]}" is not allowed: the tool manages one transaction per shard`);
}

async function recover(prefix, decision, mapping) {
  const hosts = [...new Set(SHARDS.map(s => mapping.shards[s].host))];
  for (const host of hosts) {
    const c = await connect(host, 'postgres');
    const { rows } = await c.query('SELECT gid, database FROM pg_prepared_xacts WHERE gid LIKE $1', [`${prefix}%`]);
    await c.end();
    for (const r of rows) {
      const db = await connect(host, r.database);
      await db.query(`${decision === 'commit' ? 'COMMIT' : 'ROLLBACK'} PREPARED '${r.gid}'`);
      await db.end();
      log(`${decision} ${r.gid} on ${host}/${r.database}`);
    }
  }
}

async function main() {
  const args = parse(process.argv.slice(2));
  const mapping = readMapping(args.mapping);
  if (args.recover) return recover(args.recover, args.decision, mapping);
  if (!args.file) throw new Error('Usage: shard-exec.js <file.sql> [--dry-run]');
  const sql = fs.readFileSync(args.file, 'utf8');
  check(sql);
  const run = `shard_exec_${new Date().toISOString().replace(/\D/g, '').slice(0, 14)}_${crypto.randomBytes(3).toString('hex')}`;
  log(`run ${run}: ${args.file} (${Buffer.byteLength(sql)} bytes) on 16 shards, mapping v${mapping.version}${args.dryRun ? ', DRY RUN' : ''}`);

  const started = now();
  const shards = SHARDS.map(s => ({ shard: s, ...mapping.shards[s], gid: `${run}_${s}`, status: 'pending' }));
  // Phase 1: connect, BEGIN and execute the whole file everywhere.
  await Promise.all(shards.map(async t => {
    const t0 = now();
    try {
      t.client = await connect(t.host, t.database, { application_name: 'shard-exec' });
      await t.client.query("SET lock_timeout = '10s'");
      await t.client.query('BEGIN');
      const result = await t.client.query(sql);
      const results = Array.isArray(result) ? result : [result];
      t.rows = results.map(r => r.rowCount ?? '-').join(',');
      t.status = 'executed';
    } catch (error) {
      t.status = 'FAILED';
      t.error = `${error.code || ''} ${error.message}`.trim();
    }
    t.ms = ms(t0);
  }));

  const failed = shards.filter(t => t.status !== 'executed');
  let outcome;
  if (failed.length || args.dryRun) {
    await Promise.all(shards.map(t => t.client && t.client.query('ROLLBACK').catch(() => {})));
    for (const t of shards) if (t.status === 'executed') t.status = args.dryRun ? 'rolled back (dry run)' : 'rolled back';
    outcome = failed.length ? `ROLLBACK on all 16: ${failed.length} shard(s) failed` : 'DRY RUN: everything rolled back';
  } else {
    // Phase 2: two-phase commit preparation. A failed PREPARE aborts the rest.
    let prepareError = null;
    for (const t of shards) {
      try { await t.client.query(`PREPARE TRANSACTION '${t.gid}'`); t.status = 'prepared'; }
      catch (error) { prepareError = error; t.status = 'FAILED'; t.error = `PREPARE ${error.code} ${error.message}`; break; }
    }
    if (prepareError) {
      for (const t of shards) {
        if (t.status === 'prepared') { await t.client.query(`ROLLBACK PREPARED '${t.gid}'`); t.status = 'rolled back'; }
        else if (t.status === 'executed') { await t.client.query('ROLLBACK').catch(() => {}); t.status = 'rolled back'; }
      }
      outcome = 'ROLLBACK on all 16: PREPARE failed';
    } else {
      if (args.showPrepared) {
        // Evidence for the report: every service now holds its prepared transactions.
        for (const host of [...new Set(shards.map(t => t.host))]) {
          const c = await connect(host, 'postgres');
          const { rows } = await c.query("SELECT gid, database, prepared::time(0) AS prepared FROM pg_prepared_xacts WHERE gid LIKE $1 ORDER BY gid", [`${run}%`]);
          await c.end();
          log(`pg_prepared_xacts on ${host}: ${rows.map(r => `${r.database}`).join(', ')}`);
        }
      }
      // Phase 3: all 16 voted "yes". A failure here leaves a prepared
      // transaction that --recover <run> commit finishes later.
      for (const t of shards) {
        try { await t.client.query(`COMMIT PREPARED '${t.gid}'`); t.status = 'committed'; }
        catch (error) { t.status = 'IN DOUBT'; t.error = error.message; }
      }
      const doubt = shards.filter(t => t.status === 'IN DOUBT').length;
      outcome = doubt ? `IN DOUBT on ${doubt} shard(s): run --recover ${run} commit` : 'COMMIT on all 16 shards';
    }
  }
  await Promise.all(shards.map(t => t.client && t.client.end().catch(() => {})));
  console.log(table(shards.map(t => ({ shard: t.shard, server: t.host, database: t.database, status: t.status, rows: t.rows, ms: t.ms, error: t.error })),
    ['shard', 'server', 'database', 'status', 'rows', 'ms', 'error']));
  log(`${outcome}; total ${ms(started)} ms`);
  process.exitCode = outcome.startsWith('COMMIT') || outcome.startsWith('DRY') ? 0 : 1;
}

main().catch(error => { console.error(error.message); process.exitCode = 2; });
