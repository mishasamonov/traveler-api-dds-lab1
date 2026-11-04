const express = require('express');
const shards = require('./shards');
const { shardOf, newId, query, transaction } = shards;
const { ApiError, validate, checkCombinedDates, uuid } = require('./validation');

const app = express();
app.disable('x-powered-by');
app.set('json escape', true);
app.use(express.json({ limit: '64kb' }));

const notFound = name => new ApiError(404, `${name} not found`);
const checkId = id => { if (!uuid(id)) throw new ApiError(400, 'Validation error: invalid UUID'); };
const changes = (fields, initialIndex = 1) => Object.keys(fields).map((key, i) => `${key} = $${initialIndex + i}`).join(', ');

app.get('/health', async (req, res) => {
  try {
    await shards.all('SELECT 1');
    res.json({ status: 'ok', database: 'connected', shards: 16, mapping: shards.info() });
  } catch {
    res.status(503).json({ status: 'unhealthy', database: 'disconnected' });
  }
});

// Current mapping of the 16 virtual nodes, used by tests and the report.
app.get('/api/shards', async (req, res) => {
  const map = await shards.current();
  res.json({ version: map.version, source: map.source, shards: map.shards });
});

app.get('/api/travel-plans', async (req, res) => {
  const page = Number(req.query.page || 1);
  const limit = Number(req.query.limit || 20);
  if (!Number.isSafeInteger(page) || page < 1 || !Number.isSafeInteger(limit) || limit < 1 || limit > 100 || (page - 1) * limit > 2147483647)
    throw new ApiError(400, 'Validation error: invalid pagination');
  // Two-phase scatter-gather. Phase 1: every shard returns only the sort keys
  // of its first offset+limit plans; the API merges them in the global order
  // (created_at DESC, id) and cuts the page. Phase 2: full rows and location
  // counts are read only for the ids of that page, from their own shards.
  const offset = (page - 1) * limit;
  const keys = await shards.all(`
    SELECT id, (extract(epoch FROM created_at) * 1000000)::bigint AS sort_key
    FROM travel_plans ORDER BY created_at DESC, id LIMIT $1`, [offset + limit]);
  const pageIds = keys.flatMap(part => part.rows).sort((a, b) => {
    const ka = BigInt(a.sort_key), kb = BigInt(b.sort_key);
    if (ka !== kb) return ka > kb ? -1 : 1;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  }).slice(offset, offset + limit).map(row => row.id);
  const byShard = new Map();
  for (const id of pageIds) byShard.set(shardOf(id), [...(byShard.get(shardOf(id)) || []), id]);
  const found = new Map();
  await Promise.all([...byShard].map(async ([shard, ids]) => {
    const { rows } = await query(shard, `
      SELECT p.*, COUNT(l.id)::integer AS location_count
      FROM travel_plans p LEFT JOIN locations l ON l.travel_plan_id = p.id
      WHERE p.id = ANY($1::uuid[]) GROUP BY p.id`, [ids]);
    for (const row of rows) found.set(row.id, row);
  }));
  // A plan deleted between the two phases is simply absent from the page.
  res.json(pageIds.map(id => found.get(id)).filter(Boolean));
});

app.post('/api/travel-plans', async (req, res) => {
  const fields = validate(req.body, 'plan');
  // The id is generated before INSERT: it decides which database receives the row.
  const data = { id: newId(), ...fields };
  const keys = Object.keys(data);
  const { rows } = await query(shardOf(data.id),
    `INSERT INTO travel_plans (${keys.join(', ')}) VALUES (${keys.map((_, i) => `$${i + 1}`).join(', ')}) RETURNING *`,
    Object.values(data));
  res.status(201).json(rows[0]);
});

app.get('/api/travel-plans/:id', async (req, res) => {
  checkId(req.params.id);
  const shard = shardOf(req.params.id);
  const { rows } = await query(shard, 'SELECT * FROM travel_plans WHERE id = $1', [req.params.id]);
  if (!rows.length) throw notFound('Travel plan');
  const locations = await query(shard, 'SELECT * FROM locations WHERE travel_plan_id = $1 ORDER BY visit_order', [req.params.id]);
  res.json({ ...rows[0], locations: locations.rows });
});

app.put('/api/travel-plans/:id', async (req, res) => {
  checkId(req.params.id);
  const version = req.body && req.body.version;
  const fields = validate(req.body, 'plan', true);
  const shard = shardOf(req.params.id);
  const previous = await query(shard, 'SELECT * FROM travel_plans WHERE id = $1', [req.params.id]);
  if (!previous.rows.length) throw notFound('Travel plan');
  checkCombinedDates(fields, previous.rows[0], 'plan');
  const values = Object.values(fields);
  const assignments = changes(fields);
  const { rows } = await query(shard, `UPDATE travel_plans SET ${assignments ? assignments + ', ' : ''}version = version + 1
    WHERE id = $${values.length + 1} AND version = $${values.length + 2} RETURNING *`, [...values, req.params.id, version]);
  if (!rows.length) {
    const current = await query(shard, 'SELECT version FROM travel_plans WHERE id = $1', [req.params.id]);
    if (!current.rows.length) throw notFound('Travel plan');
    throw new ApiError(409, 'Conflict: plan was modified; read it again', { current_version: current.rows[0].version });
  }
  res.json(rows[0]);
});

app.delete('/api/travel-plans/:id', async (req, res) => {
  checkId(req.params.id);
  const result = await query(shardOf(req.params.id), 'DELETE FROM travel_plans WHERE id = $1', [req.params.id]);
  if (!result.rowCount) throw notFound('Travel plan');
  res.status(204).end();
});

app.post('/api/travel-plans/:id/locations', async (req, res) => {
  checkId(req.params.id);
  const fields = validate(req.body, 'location');
  const location = await transaction(shardOf(req.params.id), async client => {
    // All inserts/reorders for this plan take the same lock before reading MAX.
    const plan = await client.query('SELECT id FROM travel_plans WHERE id = $1 FOR UPDATE', [req.params.id]);
    if (!plan.rows.length) throw notFound('Travel plan');
    const order = await client.query('SELECT COALESCE(MAX(visit_order), 0) + 1 AS next FROM locations WHERE travel_plan_id = $1', [req.params.id]);
    // Co-location: the location id ends with the same hex digit as its plan.
    const data = { id: newId(shardOf(req.params.id)), ...fields, travel_plan_id: req.params.id, visit_order: order.rows[0].next };
    const keys = Object.keys(data);
    const { rows } = await client.query(`INSERT INTO locations (${keys.join(', ')})
      VALUES (${keys.map((_, i) => `$${i + 1}`).join(', ')}) RETURNING *`, Object.values(data));
    return rows[0];
  });
  res.status(201).json(location);
});

app.put('/api/locations/:id', async (req, res) => {
  checkId(req.params.id);
  const version = req.body && req.body.version;
  const fields = validate(req.body, 'location', true);
  const location = await transaction(shardOf(req.params.id), async client => {
    // Lock the parent first, just like create, so position shifts cannot interleave.
    const parent = await client.query('SELECT travel_plan_id FROM locations WHERE id = $1', [req.params.id]);
    if (!parent.rows.length) throw notFound('Location');
    const plan = await client.query('SELECT id FROM travel_plans WHERE id = $1 FOR UPDATE', [parent.rows[0].travel_plan_id]);
    if (!plan.rows.length) throw notFound('Location');
    const current = await client.query('SELECT * FROM locations WHERE id = $1 FOR UPDATE', [req.params.id]);
    if (!current.rows.length) throw notFound('Location');
    if (current.rows[0].version !== version) throw new ApiError(409, 'Conflict: location was modified; read the plan again', { current_version: current.rows[0].version });
    checkCombinedDates(fields, current.rows[0], 'location');

    if (fields.visit_order !== undefined && fields.visit_order !== current.rows[0].visit_order) {
      const next = fields.visit_order, old = current.rows[0].visit_order;
      const max = await client.query('SELECT MAX(visit_order) AS last FROM locations WHERE travel_plan_id = $1', [parent.rows[0].travel_plan_id]);
      if (next > max.rows[0].last) throw new ApiError(400, 'Validation error: visit_order exceeds last location');
      await client.query('SET CONSTRAINTS unique_plan_order DEFERRED');
      if (next < old) await client.query('UPDATE locations SET visit_order = visit_order + 1, version = version + 1 WHERE travel_plan_id = $1 AND visit_order >= $2 AND visit_order < $3', [parent.rows[0].travel_plan_id, next, old]);
      else await client.query('UPDATE locations SET visit_order = visit_order - 1, version = version + 1 WHERE travel_plan_id = $1 AND visit_order > $2 AND visit_order <= $3', [parent.rows[0].travel_plan_id, old, next]);
    }

    const values = Object.values(fields);
    const assignment = changes(fields);
    const { rows } = await client.query(`UPDATE locations SET ${assignment ? assignment + ', ' : ''}version = version + 1
      WHERE id = $${values.length + 1} AND version = $${values.length + 2} RETURNING *`,
      [...values, req.params.id, version]);
    if (!rows.length) throw new ApiError(409, 'Conflict: location was modified; read the plan again');
    return rows[0];
  });
  res.json(location);
});

app.delete('/api/locations/:id', async (req, res) => {
  checkId(req.params.id);
  const result = await query(shardOf(req.params.id), 'DELETE FROM locations WHERE id = $1', [req.params.id]);
  if (!result.rowCount) throw notFound('Location');
  res.status(204).end();
});

app.use((error, req, res, next) => {
  if (error instanceof ApiError) return res.status(error.status).json({ error: error.message, ...error.extra });
  if (error instanceof SyntaxError && error.status === 400) return res.status(400).json({ error: 'Validation error: malformed JSON' });
  if (['23514', '22003', '22007', '22P02', '22001'].includes(error.code)) return res.status(400).json({ error: 'Validation error: invalid data' });
  if (error.code === '23505') return res.status(409).json({ error: 'Conflict: duplicate location order' });
  if (error.code === '23503') return res.status(404).json({ error: 'Travel plan not found' });
  console.error(error);
  res.status(500).json({ error: 'Internal error' });
});

module.exports = app;
