const os = require('node:os');
const fs = require('node:fs');
const { pool } = require('../src/db');
pool.query(`SELECT version() AS version,
  current_setting('default_transaction_isolation') AS isolation,
  current_setting('shared_buffers') AS shared_buffers,
  current_setting('max_connections') AS max_connections`).then(({ rows }) => {
  const data = { capturedUtc: new Date().toISOString(), cpu: os.cpus()[0].model,
    logicalCpus: os.cpus().length, memoryGB: os.totalmem()/2**30,
    node: process.version, platform: os.platform(), release: os.release(), postgres: rows[0] };
  fs.writeFileSync('tests/performance-tests/results/environment.json', JSON.stringify(data,null,2));
  console.log(JSON.stringify(data));
}).catch(e => { console.error(e);process.exitCode=1; }).finally(() => pool.end());
