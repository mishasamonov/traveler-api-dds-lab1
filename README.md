# TravelerAPI laboratory 8

Migration of the sharded TravelerAPI from relational tables to JSONB documents in
PostgreSQL: one row per travel plan with its locations embedded, the same REST API,
an atomic migration of all 16 shards (two-phase commit), a verified way back and the
laboratory 6-7 infrastructure (rebalancing, Prometheus, Grafana) working on the new
layout.

See [README-LAB8.md](README-LAB8.md). Previous laboratories: monitoring
([README-LAB7.md](README-LAB7.md)), sharding ([README-LAB6.md](README-LAB6.md)).

```powershell
python scripts/lab7/bootstrap-env.py
python scripts/lab8/lab8.py up
python scripts/lab8/lab8.py seed
python scripts/lab8/lab8.py migrate
```

Grafana: http://127.0.0.1:3001, Prometheus: http://127.0.0.1:9090.
Measured results and screenshots are in `evidence/lab8/`.
Secrets are excluded from Git and archives.
