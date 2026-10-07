'use strict';
const app = require('../src/app');
const { pool } = require('../src/db');
const port = Number(process.env.PORT || 4567);
// Restrict this lab-only launcher to the physical machine, not the LAN.
const server = app.listen(port, '127.0.0.1', () => console.log(`TravelerAPI local baseline: ${port}`));
let closing = false;
function shutdown() {
  if (closing) return;
  closing = true;
  server.close(() => pool.end().then(() => { process.exitCode = 0; }));
}
process.on('SIGTERM', shutdown);
process.on('SIGINT', shutdown);
