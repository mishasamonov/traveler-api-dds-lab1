const express = require('express');
const shards = require('./shards');
const { shardOf, newId, query, transaction } = shards;
const { ApiError, validate, checkCombinedDates, uuid } = require('./validation');
const metrics = require('./metrics');
const { planDocument, locationDocument, planPatch, locationPatch, planOut, locationOut } = require('./documents');

const app = express();
app.disable('x-powered-by');
app.set('json escape', true);
app.use(metrics.httpMiddleware);
app.use(express.json({ limit: '64kb' }));

// Laboratory 7: Prometheus scrapes this endpoint (text exposition format).
app.get('/metrics', metrics.handler);

const notFound = name => new ApiError(404, `${name} not found`);
// UUIDs are compared as text inside the documents, so they are normalised to lower case.
const checkId = id => { if (!uuid(id)) throw new ApiError(400, 'Validation error: invalid UUID'); return id.toLowerCase(); };
// Laboratory 8: one row of plan_documents = the plan with all its locations.
const PLAN = 'id, doc, version, created_at, updated_at';
// GIN (jsonb_path_ops) on doc->'locations' answers "which document contains this location".
const containsLocation = id => JSON.stringify([{ id }]);

app.get('/health', async (req, res) => {
  try {
    await shards.all('SELECT 1');
    res.json({ status: 'ok', database: 'connected', shards: 16, storage: 'jsonb', mapping: shards.info() });
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
  // Two-phase scatter-gather of laboratory 6. Phase 1: sort keys of the first
  // offset+limit plans of every shard, merged in the global order (created_at DESC, id).
  const offset = (page - 1) * limit;
  const keys = await shards.all(`
    SELECT id, (extract(epoch FROM created_at) * 1000000)::bigint AS sort_key
    FROM plan_documents ORDER BY created_at DESC, id LIMIT $1`, [offset + limit]);
  const pageIds = keys.flatMap(part => part.rows).sort((a, b) => {
    const ka = BigInt(a.sort_key), kb = BigInt(b.sort_key);
    if (ka !== kb) return ka > kb ? -1 : 1;
    return a.id < b.id ? -1 : a.id > b.id ? 1 : 0;
  }).slice(offset, offset + limit).map(row => row.id);
  const byShard = new Map();
  for (const id of pageIds) byShard.set(shardOf(id), [...(byShard.get(shardOf(id)) || []), id]);
  const found = new Map();
  // Phase 2: the documents of the page. The location count is the array
  // length - no JOIN and GROUP BY any more.
  await Promise.all([...byShard].map(async ([shard, ids]) => {
    const { rows } = await query(shard, `
      SELECT id, doc - 'locations' AS doc, version, created_at, updated_at,
             jsonb_array_length(doc->'locations') AS location_count
      FROM plan_documents WHERE id = ANY($1::uuid[])`, [ids]);
    for (const row of rows) found.set(row.id, { ...planOut(row), location_count: row.location_count });
  }));
  // A plan deleted between the two phases is simply absent from the page.
  res.json(pageIds.map(id => found.get(id)).filter(Boolean));
});

app.post('/api/travel-plans', async (req, res) => {
  const fields = validate(req.body, 'plan');
  // The id is generated before INSERT: it decides which database receives the row.
  const id = newId();
  const { rows } = await query(shardOf(id),
    `INSERT INTO plan_documents (id, doc) VALUES ($1, $2) RETURNING ${PLAN}`, [id, planDocument(fields)]);
  metrics.planCreated(shardOf(id));
  res.status(201).json(planOut(rows[0]));
});

// One indexed read instead of two queries (plan + its locations).
app.get('/api/travel-plans/:id', async (req, res) => {
  const id = checkId(req.params.id);
  const { rows } = await query(shardOf(id), `SELECT ${PLAN} FROM plan_documents WHERE id = $1`, [id]);
  if (!rows.length) throw notFound('Travel plan');
  res.json(planOut(rows[0], true));
});

app.put('/api/travel-plans/:id', async (req, res) => {
  const id = checkId(req.params.id);
  const version = req.body && req.body.version;
  const fields = validate(req.body, 'plan', true);
  const shard = shardOf(id);
  const previous = await query(shard, `SELECT doc - 'locations' AS doc FROM plan_documents WHERE id = $1`, [id]);
  if (!previous.rows.length) throw notFound('Travel plan');
  checkCombinedDates(fields, previous.rows[0].doc, 'plan');
  // || replaces only the given top-level keys; the locations stay untouched.
  const { rows } = await query(shard, `UPDATE plan_documents SET doc = doc || $1::jsonb, version = version + 1, updated_at = now()
    WHERE id = $2 AND version = $3 RETURNING id, doc - 'locations' AS doc, version, created_at, updated_at`,
  [planPatch(fields), id, version]);
  if (!rows.length) {
    const current = await query(shard, 'SELECT version FROM plan_documents WHERE id = $1', [id]);
    if (!current.rows.length) throw notFound('Travel plan');
    throw new ApiError(409, 'Conflict: plan was modified; read it again', { current_version: current.rows[0].version });
  }
  res.json(planOut(rows[0]));
});

// The locations are inside the document: deleting the row is the cascade.
app.delete('/api/travel-plans/:id', async (req, res) => {
  const id = checkId(req.params.id);
  const result = await query(shardOf(id), 'DELETE FROM plan_documents WHERE id = $1', [id]);
  if (!result.rowCount) throw notFound('Travel plan');
  res.status(204).end();
});

// One atomic UPDATE: the row lock of the document replaces SELECT ... FOR UPDATE,
// and the next visit_order is computed from the same version of the document.
app.post('/api/travel-plans/:id/locations', async (req, res) => {
  const planId = checkId(req.params.id);
  const fields = validate(req.body, 'location');
  // Co-location: the location id ends with the same hex digit as its plan.
  const location = locationDocument(newId(shardOf(planId)), fields);
  const { rows } = await query(shardOf(planId), `
    UPDATE plan_documents
    SET doc = jsonb_set(doc, '{locations}', doc->'locations' || jsonb_build_array($2::jsonb || jsonb_build_object(
      'visit_order', (SELECT coalesce(max((l->>'visit_order')::int), 0) + 1 FROM jsonb_array_elements(doc->'locations') l),
      'created_at', now())))
    WHERE id = $1
    RETURNING doc->'locations'->-1 AS location`, [planId, location]);
  if (!rows.length) throw notFound('Travel plan');
  res.status(201).json(locationOut(rows[0].location, planId));
});

// Read - change - write of one document under its row lock.
app.put('/api/locations/:id', async (req, res) => {
  const id = checkId(req.params.id);
  const version = req.body && req.body.version;
  const fields = validate(req.body, 'location', true);
  const location = await transaction(shardOf(id), async client => {
    const { rows } = await client.query(`SELECT id, doc->'locations' AS locations FROM plan_documents
      WHERE doc->'locations' @> $1::jsonb FOR UPDATE`, [containsLocation(id)]);
    if (!rows.length) throw notFound('Location');
    const planId = rows[0].id, list = rows[0].locations;
    const current = list.find(l => l.id === id);
    if (current.version !== version) throw new ApiError(409, 'Conflict: location was modified; read the plan again', { current_version: current.version });
    checkCombinedDates(fields, current, 'location');

    if (fields.visit_order !== undefined && fields.visit_order !== current.visit_order) {
      const next = fields.visit_order, old = current.visit_order;
      if (next > Math.max(...list.map(l => l.visit_order))) throw new ApiError(400, 'Validation error: visit_order exceeds last location');
      // The same shift as the relational version: neighbours move by one and get a new version.
      for (const l of list) {
        if (l === current) continue;
        if (next < old && l.visit_order >= next && l.visit_order < old) { l.visit_order += 1; l.version += 1; }
        if (next > old && l.visit_order > old && l.visit_order <= next) { l.visit_order -= 1; l.version += 1; }
      }
    }
    Object.assign(current, locationPatch(fields), { version: current.version + 1 });
    list.sort((a, b) => a.visit_order - b.visit_order);
    await client.query(`UPDATE plan_documents SET doc = jsonb_set(doc, '{locations}', $2::jsonb) WHERE id = $1`, [planId, JSON.stringify(list)]);
    return locationOut(current, planId);
  });
  res.json(location);
});

// Remove one element of the array; the remaining locations keep their order (gaps allowed, as before).
app.delete('/api/locations/:id', async (req, res) => {
  const id = checkId(req.params.id);
  const result = await query(shardOf(id), `
    UPDATE plan_documents
    SET doc = jsonb_set(doc, '{locations}', (SELECT coalesce(jsonb_agg(l ORDER BY n), '[]'::jsonb)
                                            FROM jsonb_array_elements(doc->'locations') WITH ORDINALITY e(l, n)
                                            WHERE l->>'id' <> $2))
    WHERE doc->'locations' @> $1::jsonb`, [containsLocation(id), id]);
  if (!result.rowCount) throw notFound('Location');
  res.status(204).end();
});

app.use((error, req, res, next) => {
  if (error instanceof ApiError) return res.status(error.status).json({ error: error.message, ...error.extra });
  if (error instanceof SyntaxError && error.status === 400) return res.status(400).json({ error: 'Validation error: malformed JSON' });
  // 23514: the CHECK plan_document_valid; 22P05: \u0000 is not allowed in jsonb text.
  if (['23514', '22003', '22007', '22P02', '22001', '22P05'].includes(error.code)) return res.status(400).json({ error: 'Validation error: invalid data' });
  console.error(error);
  res.status(500).json({ error: 'Internal error' });
});

module.exports = app;
