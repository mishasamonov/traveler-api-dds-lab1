# TravelerAPI laboratory 7

Monitoring of the sharded TravelerAPI with Prometheus and Grafana: prom-client metrics in
the API, one postgres_exporter per PostgreSQL service, alerting rules and two provisioned
Grafana dashboards.

See [README-LAB7.md](README-LAB7.md). Previous laboratory: sharding
([README-LAB6.md](README-LAB6.md)).

```powershell
python scripts/lab7/bootstrap-env.py
python scripts/lab7/lab7.py up
python scripts/lab7/lab7.py seed
```

Grafana: http://127.0.0.1:3000, Prometheus: http://127.0.0.1:9090.
Measured results and screenshots are in `evidence/lab7/`.
Secrets are excluded from Git and archives.
