// Laboratory 7: Prometheus metrics of TravelerAPI (prom-client).
// GET /metrics returns the text exposition format that Prometheus scrapes.
// Labels are kept bounded: route templates instead of raw URLs, 16 shards,
// 4 PostgreSQL services, HTTP status codes and PostgreSQL error codes.
const client = require('prom-client');

// METRICS=off turns the instrumentation into no-ops (used to measure its overhead).
const ENABLED = process.env.METRICS !== 'off';

const register = new client.Registry();
register.setDefaultLabels({ app: 'traveler-api' });
// Node.js process metrics: CPU, memory, event loop lag, GC, active handles.
client.collectDefaultMetrics({ register });

const HTTP_BUCKETS = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 0.75, 1, 1.5, 2, 2.5, 5];
const DB_BUCKETS = [0.0005, 0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5];

const httpDuration = new client.Histogram({
  name: 'http_request_duration_seconds',
  help: 'HTTP request duration by route template and status code',
  labelNames: ['method', 'route', 'status'], buckets: HTTP_BUCKETS, registers: [register],
});
const httpInFlight = new client.Gauge({
  name: 'http_requests_in_flight', help: 'HTTP requests being processed now', registers: [register],
});
const dbQueryDuration = new client.Histogram({
  name: 'db_query_duration_seconds',
  help: 'Duration of one SQL statement (or one whole transaction) on a shard',
  labelNames: ['shard', 'server', 'kind', 'outcome'], buckets: DB_BUCKETS, registers: [register],
});
const dbErrors = new client.Counter({
  name: 'db_errors_total', help: 'Failed statements by shard and PostgreSQL SQLSTATE',
  labelNames: ['shard', 'server', 'code'], registers: [register],
});
const scatterGather = new client.Histogram({
  name: 'scatter_gather_duration_seconds', help: 'The same statement on all 16 shards in parallel (list, health)',
  buckets: HTTP_BUCKETS, registers: [register],
});
const shardRetries = new client.Counter({
  name: 'shard_retries_total', help: 'Requests repeated on a new server after the shard was moved',
  labelNames: ['shard'], registers: [register],
});
const mappingReloads = new client.Counter({
  name: 'shard_mapping_reloads_total', help: 'Mapping reloads: startup or the SQLSTATE that triggered it',
  labelNames: ['trigger'], registers: [register],
});
const mappingVersion = new client.Gauge({
  name: 'shard_mapping_version', help: 'Version of the shard mapping used by this API instance', registers: [register],
});
const shardServer = new client.Gauge({
  name: 'shard_server_info', help: '1 for the PostgreSQL service that currently owns each shard',
  labelNames: ['shard', 'server', 'database'], registers: [register],
});
const plansCreated = new client.Counter({
  name: 'travel_plans_created_total', help: 'Travel plans created through the API, by shard',
  labelNames: ['shard'], registers: [register],
});

// Pool statistics are read at scrape time from the live pg.Pool objects.
let poolSource = () => [];
new client.Gauge({
  name: 'db_pool_connections', help: 'pg.Pool connections per database: total, idle and waiting clients',
  labelNames: ['database', 'server', 'state'], registers: [register],
  collect() {
    this.reset();
    for (const p of poolSource()) {
      this.set({ database: p.database, server: p.server, state: 'total' }, p.total);
      this.set({ database: p.database, server: p.server, state: 'idle' }, p.idle);
      this.set({ database: p.database, server: p.server, state: 'waiting' }, p.waiting);
    }
  },
});

// Route label: the matched Express template (/api/travel-plans/:id), never the raw URL.
function httpMiddleware(req, res, next) {
  if (!ENABLED || req.path === '/metrics') return next();
  httpInFlight.inc();
  const end = httpDuration.startTimer({ method: req.method });
  let done = false;
  const finish = () => {
    if (done) return;
    done = true;
    httpInFlight.dec();
    const route = req.route ? req.baseUrl + req.route.path : 'unmatched';
    end({ route, status: String(res.statusCode) });
  };
  res.on('finish', finish);
  res.on('close', finish);
  next();
}

async function observe(shard, target, kind, run) {
  if (!ENABLED) return run();
  const end = dbQueryDuration.startTimer({ shard, server: target.host, kind });
  try {
    const result = await run();
    end({ outcome: 'ok' });
    return result;
  } catch (error) {
    // ApiError (404/409) inside a transaction is a business rollback, not a database failure.
    if (error.status) { end({ outcome: 'rollback' }); throw error; }
    end({ outcome: 'error' });
    const code = error.code || (/timeout/i.test(error.message) ? 'pool_timeout' : 'unknown');
    dbErrors.inc({ shard, server: target.host, code });
    throw error;
  }
}

function mappingLoaded(mapping, trigger) {
  mappingReloads.inc({ trigger });
  mappingVersion.set(mapping.version);
  shardServer.reset();
  for (const [shard, t] of Object.entries(mapping.shards)) {
    shardServer.set({ shard, server: t.host, database: t.database }, 1);
    // Expected series start at 0, otherwise increase() misses the first 42501 after a move.
    for (const code of ['42501', '3D000']) dbErrors.inc({ shard, server: t.host, code }, 0);
    shardRetries.inc({ shard }, 0);
  }
}

async function handler(req, res) {
  if (!ENABLED) return res.status(404).json({ error: 'Metrics are disabled (METRICS=off)' });
  res.set('Content-Type', register.contentType);
  res.end(await register.metrics());
}

module.exports = {
  register, httpMiddleware, handler, observe, mappingLoaded,
  setPoolSource: fn => { poolSource = fn; },
  timeScatter: () => scatterGather.startTimer(),
  retried: shard => shardRetries.inc({ shard }),
  planCreated: shard => plansCreated.inc({ shard }),
};
