# TravelerAPI - laboratory 7: monitoring with Prometheus + Grafana

Variant 4 of the "cosmetic" laboratory: monitoring of the sharded TravelerAPI from
laboratory 6 (16 databases `db_0..db_f` on four PostgreSQL services, two API instances).

| Component | What it provides |
|-----------|------------------|
| `src/metrics.js` (prom-client) | `GET /metrics` of each API: HTTP rate/latency/status by route template, SQL statements per shard and server, pool state of the 16 `pg.Pool`s, mapping version, shard placement, retries after a shard move, Node.js process metrics |
| `pg_exporter_00..03` | one `postgres_exporter` per PostgreSQL service: `pg_stat_database` per database (= per shard), database size, connections, locks, replication slots of `shard_registry` |
| `prometheus` | scrapes every 5 s, evaluates `monitoring/prometheus/alerts.yml`, receives k6 metrics (remote write) |
| `grafana` | provisioned datasource and two dashboards from `monitoring/grafana` |

The monitoring is an overlay: [`docker-compose.monitoring.yml`](docker-compose.monitoring.yml)
is used together with the unchanged `docker-compose.lab6.yml`.

## Run

```powershell
python scripts/lab7/bootstrap-env.py      # adds MONITOR_PASSWORD and GRAFANA_ADMIN_PASSWORD to .env
python scripts/lab7/lab7.py up            # traveler_lab7: 4 PostgreSQL, 2 API, 4 exporters, Prometheus, Grafana
python scripts/lab7/lab7.py seed          # laboratory 2 dataset in 16 shards
python scripts/lab7/lab7.py hurl          # 5 Hurl files, including tests/metrics.hurl
```

* Grafana: <http://127.0.0.1:3000> (anonymous Viewer; `admin` / `GRAFANA_ADMIN_PASSWORD` for editing)
* Prometheus: <http://127.0.0.1:9090> (targets, alerts, PromQL)
* API metrics: <http://127.0.0.1:4567/metrics>, <http://127.0.0.1:4568/metrics>

Dashboards are generated from PromQL definitions: `python scripts/lab7/dashboards.py`.

## Experiments

```powershell
python scripts/lab7/lab7.py load        # k6 Load of laboratory 2, k6 metrics -> Prometheus
python scripts/lab7/lab7.py hotspot     # traffic only to shard 5 -> alert ShardHotspot
python scripts/lab7/lab7.py failure     # postgres_02 stopped for ~50 s -> PostgresDown, 5xx for shards 8..b
python scripts/lab7/lab7.py rebalance   # laboratory 6 rebalance.js moves db_3 and db_7 under load
```

## Alerts

`TravelerApiDown`, `TravelerApiHighErrorRate`, `TravelerApiHighLatencyP95`, `ShardDatabaseErrors`,
`ShardPoolSaturated`, `ShardHotspot`, `ShardMappingVersionMismatch`, `PostgresDown`,
`PostgresExporterDown`, `PostgresTooManyConnections`, `RegistryReplicationSlotInactive`.

## Security

* `postgres_exporter` logs in as `lab7_monitor`: `pg_monitor` only, `CONNECTION LIMIT 5`,
  `pg_hba.conf` allows it only to the `postgres` database.
* Exporters stay in the internal `backend` network; only Prometheus (9090) and Grafana (3000)
  are published, and only on `127.0.0.1`.
* Metric labels are bounded (route templates, 16 shards, 4 servers), ids never become labels.
