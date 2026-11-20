// CI of laboratory 8: 16 shard databases inside the single PostgreSQL service
// of the workflow, a mapping file where every shard points to localhost, and
// the whole migration path of the laboratory on every database:
//   001_schema.sql (relational, laboratories 2-7) -> laboratory 2 dataset
//   -> 002_plan_documents.sql + sql/100_migrate_to_jsonb.sql (with its row check)
//   -> way back 001 + sql/190_rollback_to_relational.sql inside a transaction
//      that is rolled back: it must reproduce the fingerprint of the old rows
//   -> sql/110_drop_legacy.sql
// so a broken migration fails the build before the Hurl tests start.
const fs = require('node:fs');
const path = require('node:path');
const { Client } = require('pg');

const root = path.join(__dirname, '../..');
const url = new URL(process.env.DATABASE_URL || 'postgres://traveler:traveler@localhost:5432/traveler');
const target = process.env.MAPPING_FILE || '.runtime/ci-mapping.json';
const read = file => fs.readFileSync(path.join(root, file), 'utf8');
const ROUND_TRIP = 'round trip';
const steps = [
  ['db/migrations/001_schema.sql'],
  ['sql/000_seed_lab2_dataset.sql'],
  ['db/migrations/002_plan_documents.sql', 'sql/100_migrate_to_jsonb.sql'],
  [ROUND_TRIP, 'db/migrations/001_schema.sql', 'sql/190_rollback_to_relational.sql'],
  ['sql/110_drop_legacy.sql'],
];

(async () => {
  const shards = {};
  for (const s of '0123456789abcdef') {
    const database = `db_${s}`;
    const admin = new Client({ connectionString: url.href });
    await admin.connect();
    await admin.query(`DROP DATABASE IF EXISTS ${database}`);
    await admin.query(`CREATE DATABASE ${database}`);
    await admin.end();
    const db = new Client({ connectionString: Object.assign(new URL(url.href), { pathname: `/${database}` }).href });
    await db.connect();
    const results = [];
    for (const step of steps) {
      const dryRun = step[0] === ROUND_TRIP, files = dryRun ? step.slice(1) : step;
      await db.query('BEGIN');
      const result = await db.query(files.map(read).join('\n'));
      const last = [].concat(result).pop();
      await db.query(dryRun ? 'ROLLBACK' : 'COMMIT');
      if (dryRun && last.rows[0].same_as_before !== true) throw new Error(`${database}: the way back changed the data`);
      if (last && last.rows && last.rows.length) results.push(JSON.stringify(last.rows[0]));
    }
    await db.end();
    console.log(`${database}: ${results.join(' ')}`);
    shards[s] = { host: url.hostname, port: Number(url.port || 5432), database };
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, JSON.stringify({ version: 1, description: 'CI: 16 shards in one PostgreSQL', shards }, null, 2));
  console.log(`created db_0..db_f on ${url.hostname} (migrated to JSONB); mapping ${target}`);
})().catch(error => { console.error(error); process.exit(1); });
