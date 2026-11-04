// CI: 16 shard databases inside the single PostgreSQL service of the workflow,
// plus a mapping file where every shard points to localhost.
const fs = require('node:fs');
const path = require('node:path');
const { Client } = require('pg');

const url = new URL(process.env.DATABASE_URL || 'postgres://traveler:traveler@localhost:5432/traveler');
const schema = fs.readFileSync(path.join(__dirname, '../../db/migrations/001_schema.sql'), 'utf8');
const target = process.env.MAPPING_FILE || '.runtime/ci-mapping.json';

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
    await db.query(schema);
    await db.end();
    shards[s] = { host: url.hostname, port: Number(url.port || 5432), database };
  }
  fs.mkdirSync(path.dirname(target), { recursive: true });
  fs.writeFileSync(target, JSON.stringify({ version: 1, description: 'CI: 16 shards in one PostgreSQL', shards }, null, 2));
  console.log(`created db_0..db_f on ${url.hostname}; mapping ${target}`);
})().catch(error => { console.error(error); process.exit(1); });
