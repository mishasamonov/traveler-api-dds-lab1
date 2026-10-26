const fs = require('node:fs');
const { pool } = require('../src/db');
(async () => {
  const { rows } = await pool.query(`SELECT
    (SELECT count(*)::int FROM travel_plans) AS plans,
    (SELECT count(*)::int FROM locations) AS locations,
    (SELECT count(*)::int FROM travel_plans WHERE title LIKE 'k6 temporary%') AS temporary_plans,
    (SELECT count(*)::int FROM locations l LEFT JOIN travel_plans p ON l.travel_plan_id=p.id WHERE p.id IS NULL) AS orphan_locations`);
  const result = { checkedUtc: new Date().toISOString(), ...rows[0] };
  fs.writeFileSync(`tests/performance-tests/results/${process.argv[2]}-data-check.json`, JSON.stringify(result,null,2));
  console.log(JSON.stringify(result));
})().catch(e => {console.error(e);process.exitCode=1;}).finally(() => pool.end());
