const { Pool, types } = require('pg');

types.setTypeParser(1082, value => value); // DATE stays YYYY-MM-DD in JSON.
types.setTypeParser(1700, value => Number(value)); // NUMERIC values in the API.

const pool = new Pool({
  connectionString: process.env.DATABASE_URL || 'postgres://traveler:traveler@localhost:5432/traveler',
  max: Number(process.env.PG_POOL_MAX || 20),
  connectionTimeoutMillis: 5000,
});

async function transaction(fn) {
  const client = await pool.connect();
  try {
    await client.query('BEGIN');
    const result = await fn(client);
    await client.query('COMMIT');
    return result;
  } catch (error) {
    await client.query('ROLLBACK');
    throw error;
  } finally {
    client.release();
  }
}

module.exports = { pool, transaction };
