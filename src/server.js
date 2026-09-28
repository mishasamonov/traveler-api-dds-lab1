const app = require('./app');
const { pool } = require('./db');
const port = Number(process.env.PORT || 4567);

const server = app.listen(port, () => console.log(`Traveler API listening on ${port}`));
function shutdown() { server.close(() => pool.end().then(() => process.exit(0))); }
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
