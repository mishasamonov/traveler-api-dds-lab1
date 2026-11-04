// Shared helpers for the laboratory 6 CLI tools (run inside the backend network).
const fs = require('node:fs');
const path = require('node:path');
const { Client } = require('pg');

const SHARDS = '0123456789abcdef'.split('');
const MAPPING_FILE = process.env.MAPPING_FILE || 'config/mapping.json';
const admin = { user: process.env.DB_ADMIN, password: process.env.DB_ADMIN_PASSWORD };

function readMapping(file = MAPPING_FILE) { return JSON.parse(fs.readFileSync(file, 'utf8')); }

// Atomic replace: write a temporary file next to the mapping and rename it.
function writeMapping(mapping, file = MAPPING_FILE) {
  const tmp = path.join(path.dirname(file), `.mapping.${process.pid}.tmp`);
  fs.writeFileSync(tmp, JSON.stringify(mapping, null, 2) + '\n');
  fs.renameSync(tmp, file);
}

async function connect(host, database, extra = {}) {
  const client = new Client({ host, port: 5432, database, ...admin, connectionTimeoutMillis: 5000, ...extra });
  // A server-side termination must surface as a failed query, not crash the tool.
  client.on('error', error => log(`   connection ${host}/${database} closed by server: ${error.code || error.message}`));
  await client.connect();
  return client;
}

const ident = value => {
  if (!/^[a-z_][a-z0-9_]*$/.test(value)) throw new Error(`Unsafe identifier ${value}`);
  return value;
};
const ms = start => Math.round(Number(process.hrtime.bigint() - start) / 1e6);
const now = () => process.hrtime.bigint();
const log = (...args) => console.log(new Date().toISOString().slice(11, 23), ...args);

function table(rows, columns) {
  const width = columns.map(c => Math.max(c.length, ...rows.map(r => String(r[c] ?? '').length)));
  const line = values => values.map((v, i) => String(v ?? '').padEnd(width[i])).join(' | ');
  return [line(columns), width.map(w => '-'.repeat(w)).join('-+-'), ...rows.map(r => line(columns.map(c => r[c])))].join('\n');
}

module.exports = { SHARDS, MAPPING_FILE, readMapping, writeMapping, connect, ident, ms, now, log, table, admin };
