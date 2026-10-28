const { pool } = require('../src/db');
(async () => {
  const { rows } = await pool.query(`SELECT
    (SELECT count(*)::int FROM travel_plans) AS plans,
    (SELECT count(*)::int FROM locations) AS locations,
    (SELECT count(*)::int FROM travel_plans WHERE title LIKE 'k6 temporary%') AS temporary_plans,
    (SELECT count(*)::int FROM locations l LEFT JOIN travel_plans p ON l.travel_plan_id=p.id WHERE p.id IS NULL) AS orphan_locations`);
  const r = { checkedUtc: new Date().toISOString(), ...rows[0] };
  console.log(JSON.stringify(r, null, 2));
  if (r.plans !== 2000 || r.locations !== 6000 || r.temporary_plans || r.orphan_locations) process.exitCode = 1;
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(() => pool.end());
