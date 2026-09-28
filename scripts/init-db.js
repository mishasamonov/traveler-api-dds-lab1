const fs = require('node:fs');
const path = require('node:path');
const { pool } = require('../src/db');

(async () => {
  try {
    const sql = fs.readFileSync(path.join(__dirname, '../db/schema.sql'), 'utf8');
    await pool.query(sql);
    const migration = fs.readFileSync(path.join(__dirname, '../db/002_location_version.sql'), 'utf8');
    await pool.query(migration);
    console.log('PostgreSQL schema applied');
  } finally {
    await pool.end();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
