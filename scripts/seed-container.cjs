// Exactly the laboratory 2 dataset, in an explicitly opted-in disposable database.
const { pool } = require('../src/db');
(async () => {
  const { rows: db } = await pool.query('SELECT current_database() AS name');
  if (process.env.LAB3_ALLOW_RESET !== 'true' || db[0].name !== 'traveler_lab2')
    throw new Error('Reset requires LAB3_ALLOW_RESET=true and disposable traveler_lab2');
  await pool.query('TRUNCATE locations, travel_plans');
  await pool.query(`INSERT INTO travel_plans(id,title,description,budget,currency)
    SELECT md5('lab2-plan-' || i)::uuid, 'Baseline trip ' || i, repeat('Travel itinerary ',8), 1000, 'EUR'
    FROM generate_series(1,2000) AS i`);
  await pool.query(`INSERT INTO locations(id,travel_plan_id,name,visit_order,latitude,longitude,budget)
    SELECT md5('lab2-location-' || i || '-' || j)::uuid, md5('lab2-plan-' || i)::uuid,
    'Location ' || j, j, 48.8566, 2.3522, 100
    FROM generate_series(1,2000) AS i CROSS JOIN generate_series(1,3) AS j`);
  await pool.query('ANALYZE travel_plans; ANALYZE locations');
  const { rows } = await pool.query('SELECT id FROM travel_plans ORDER BY id');
  process.stdout.write(JSON.stringify(rows));
})().catch(e => { console.error(e); process.exitCode = 1; }).finally(() => pool.end());
