# TravelerAPI laboratory 4

Logical and physical PostgreSQL replication, synchronous commit, two replicas,
restricted credentials/network exposure, and PgCat read/write routing. Continues
the laboratory 3 Node.js API. `src/`, original Hurl tests and mixed k6 workload are unchanged.

Instructor reference: https://github.com/potapuff/SumDU.DDS.25F.example/commit/cd66c0f22e08f61602834d4edad4fd82ed672f1a

## Start

Requires Docker Desktop Linux containers, Python 3, and k6 for load tests.

```powershell
python scripts/lab4/bootstrap-env.py
python scripts/lab4/lab.py up logical
python scripts/lab4/lab.py functional logical
python scripts/lab4/lab.py seed logical
python scripts/lab4/lab.py proof logical
```

API: http://127.0.0.1:4567/health . The default `.env` also supports
`docker compose up --build` for one logical subscriber. Bootstrap with **new named
volumes in a new Compose project**; old laboratory volumes are preserved.
Initialisation scripts run only on the first start of a volume.

## Modes

| Mode | Data path |
| --- | --- |
| baseline | API -> primary, no subscriber |
| logical | API -> publisher -> one logical subscriber |
| logical2 | API -> publisher -> two independent logical subscribers and slots |
| physical | API -> primary -> asynchronous physical standby |
| sync | API -> primary -> `FIRST 1 (replica1)`, `remote_apply` |
| two | API -> primary -> two physical replicas, `ANY 2`, `remote_apply` |
| pgcat | API -> PgCat; writes -> primary, reads -> both physical replicas |

```powershell
python scripts/lab4/lab.py up pgcat
python scripts/lab4/lab.py proof pgcat
python scripts/lab4/lab.py benchmark pgcat --test smoke --k6 C:/path/to/k6.exe
python scripts/lab4/lab.py benchmark pgcat --test load --k6 C:/path/to/k6.exe
python scripts/lab4/run-suite.py --k6 C:/path/to/k6.exe
```

The wrapper selects Compose profiles, unique project/subnet names, starts replicas
before enabling synchronous commit, then starts the API. The previous **lab4**
project recorded in `.runtime/active.json` is stopped; its volumes remain.
Experiments are sequential and share the same local API port.

## Reproducibility and measurements

Every k6 run seeds exactly 2,000 plans and 6,000 locations using the lab2 SQL.
Full row checksums must converge before measurement. The original mixed load is
170 seconds, stages 25/50/100/200 VU. Smoke is the original 20-second scenario.
`read-test.js` is a separate 45-second, 200-VU read-only control, repeated three
times for direct access and PgCat using the same two-replica synchronous topology.
All configurations keep `wal_level=logical` so the main comparison isolates
active replication rather than also changing WAL level. Each PostgreSQL service
has 2 CPU/1 GiB, API 2 CPU/512 MiB, PgCat 1 CPU/256 MiB.

Output is under `evidence/lab4/`: native command output, k6 JSON summaries,
raw compressed events, Docker telemetry, data equality, DDL behaviour,
synchronous blocking proof, and actual PgCat backend distribution. A load test
exit code 99 indicates a threshold breach and is reported as such.

Physical standby bootstrap uses `pg_basebackup -R -X stream` and separate physical
slots. DDL is replayed with WAL; logical DDL is applied separately and the
publication refreshed. `wal_keep_size=256MB` protects concurrent standby bootstrap;
an existing named physical slot is reused after an interrupted base backup. The
`sync` experiment pauses the replica briefly and observes the
primary's `SyncRep` wait before resuming it. No availability claim is made:
requiring both replicas with `ANY 2` blocks writes if either is unavailable.

## Security

Independent admin/application/replication roles; app has no superuser, replication,
CREATE ROLE, CREATE DATABASE or TRUNCATE permissions. Secrets are generated locally,
passed through environment variables, and excluded from Git/build context/archive.
PgCat config is rendered under ignored `.runtime/`, not committed.
No PostgreSQL or PgCat host ports are published. Only API binds to loopback.
Database network is `internal`; only API additionally joins a frontend network.
`pg_hba.conf` admits named roles from the project's CIDR with SCRAM and rejects
other IPv4/IPv6 hosts. Local socket trust is confined to a container; Docker access
is administrative access. This local lab does not configure TLS between containers.

## Notes about consistency

PgCat reads go only to replicas. Both physical standbys are synchronous with
`synchronous_commit=remote_apply` so a completed API write is replayed on both
before subsequent reads may be routed to either. Async read/write splitting
alone does not provide this guarantee. Explicit write transactions start on
the primary (`default_role=primary`). The routing evidence checks two replica
addresses for SELECT and the primary address for UPDATE RETURNING.

## Sources

- PostgreSQL logical limitations: https://www.postgresql.org/docs/16/logical-replication-restrictions.html
- PostgreSQL synchronous replication: https://www.postgresql.org/docs/16/warm-standby.html#SYNCHRONOUS-REPLICATION
- `remote_apply`: https://www.postgresql.org/docs/16/runtime-config-wal.html
- PgCat settings: https://github.com/postgresml/pgcat/blob/main/pgcat.toml

PostgreSQL can also use logical subscribers as synchronous standbys. The logical
variant in this experiment is asynchronous; the exercise's blanket statement
that logical replication is exclusively asynchronous is a simplification.
