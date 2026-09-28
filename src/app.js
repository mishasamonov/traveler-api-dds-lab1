const express = require('express');
const { pool, transaction } = require('./db');
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
    await pool.query('SELECT 1');
    res.json({ status: 'ok', database: 'connected' });
  } catch {
    res.status(503).json({ status: 'unhealthy', database: 'disconnected' });
  }
});

app.get('/api/travel-plans', async (req, res) => {
  const page = Number(req.query.page || 1);
  const limit = Number(req.query.limit || 20);
  if (!Number.isSafeInteger(page) || page < 1 || !Number.isSafeInteger(limit) || limit < 1 || limit > 100 || (page - 1) * limit > 2147483647)
    throw new ApiError(400, 'Validation error: invalid pagination');
  const { rows } = await pool.query(`
    SELECT p.*, COUNT(l.id)::integer AS location_count
    FROM travel_plans p LEFT JOIN locations l ON l.travel_plan_id = p.id
    GROUP BY p.id ORDER BY p.created_at DESC, p.id LIMIT $1 OFFSET $2`, [limit, (page - 1) * limit]);
  res.json(rows);
});

app.post('/api/travel-plans', async (req, res) => {
  const fields = validate(req.body, 'plan');
  const keys = Object.keys(fields);
  const { rows } = await pool.query(
    `INSERT INTO travel_plans (${keys.join(', ')}) VALUES (${keys.map((_, i) => `$${i + 1}`).join(', ')}) RETURNING *`,
    Object.values(fields));
  res.status(201).json(rows[0]);
});

app.get('/api/travel-plans/:id', async (req, res) => {
  checkId(req.params.id);
  const { rows } = await pool.query('SELECT * FROM travel_plans WHERE id = $1', [req.params.id]);
  if (!rows.length) throw notFound('Travel plan');
  const locations = await pool.query('SELECT * FROM locations WHERE travel_plan_id = $1 ORDER BY visit_order', [req.params.id]);
  res.json({ ...rows[0], locations: locations.rows });
});

app.put('/api/travel-plans/:id', async (req, res) => {
  checkId(req.params.id);
  const version = req.body && req.body.version;
  const fields = validate(req.body, 'plan', true);
  const previous = await pool.query('SELECT * FROM travel_plans WHERE id = $1', [req.params.id]);
  if (!previous.rows.length) throw notFound('Travel plan');
  checkCombinedDates(fields, previous.rows[0], 'plan');
  const values = Object.values(fields);
  const assignments = changes(fields);
  const { rows } = await pool.query(`UPDATE travel_plans SET ${assignments ? assignments + ', ' : ''}version = version + 1
    WHERE id = $${values.length + 1} AND version = $${values.length + 2} RETURNING *`, [...values, req.params.id, version]);
  if (!rows.length) {
    const current = await pool.query('SELECT version FROM travel_plans WHERE id = $1', [req.params.id]);
    if (!current.rows.length) throw notFound('Travel plan');
    throw new ApiError(409, 'Conflict: plan was modified; read it again', { current_version: current.rows[0].version });
  }
  res.json(rows[0]);
});

app.delete('/api/travel-plans/:id', async (req, res) => {
  checkId(req.params.id);
  const result = await pool.query('DELETE FROM travel_plans WHERE id = $1', [req.params.id]);
  if (!result.rowCount) throw notFound('Travel plan');
  res.status(204).end();
});

app.post('/api/travel-plans/:id/locations', async (req, res) => {
  checkId(req.params.id);
  const fields = validate(req.body, 'location');
  const location = await transaction(async client => {
    // All inserts/reorders for this plan take the same lock before reading MAX.
    const plan = await client.query('SELECT id FROM travel_plans WHERE id = $1 FOR UPDATE', [req.params.id]);
    if (!plan.rows.length) throw notFound('Travel plan');
    const order = await client.query('SELECT COALESCE(MAX(visit_order), 0) + 1 AS next FROM locations WHERE travel_plan_id = $1', [req.params.id]);
    const data = { ...fields, travel_plan_id: req.params.id, visit_order: order.rows[0].next };
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
  const location = await transaction(async client => {
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
  const result = await pool.query('DELETE FROM locations WHERE id = $1', [req.params.id]);
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
