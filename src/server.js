const app = require('./app');
const shards = require('./shards');
const port = Number(process.env.PORT || 4567);

// Load the mapping before accepting requests; a broken mapping stops startup.
shards.reload('startup').then(() => {
  const server = app.listen(port, () => console.log(`Traveler API listening on ${port} (16 shards)`));
  function shutdown() { server.close(() => shards.end().then(() => process.exit(0))); }
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
}).catch(error => { console.error(error); process.exit(1); });
