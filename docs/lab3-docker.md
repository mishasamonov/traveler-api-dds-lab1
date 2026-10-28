# Laboratory 3 Docker deployment

This branch continues `lab2-performance`. The API, SQL schema, dependency lockfile,
Hurl files and k6 workload are unchanged. Baseline measurements remain in
`tests/performance-tests/results`; new measurements are in `results-docker`.

## Start

1. Copy `.env.example` to `.env`. Replace the example password in both
   `DB_PASSWORD` and `DATABASE_URL`. Use URL-safe characters or percent-encode the
   password in the URL. `.env` must remain untracked.
2. Run `docker --version`, `docker compose build`, then `docker compose up -d --wait`.
   The single command `docker compose up --build` also starts the entire project.
3. Open http://localhost:4567/health. PostgreSQL is private to the Compose network.
4. Inspect `docker compose ps`, `docker compose logs -f web`, and `docker stats`.

The default Compose configuration is the measured production configuration.
It uses an unprivileged API process, a read-only application filesystem,
healthchecks, log rotation, a persistent PostgreSQL named volume and per-service
resource limits. The official PostgreSQL entrypoint initializes the volume and
drops privileges to the `postgres` account for the database process.

Development: `docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build`.
The development override mounts source read-only for `node --watch` and selects a
separate database volume. Stop the production stack before switching modes.
Update available images with `docker compose pull` and rebuild the application
with `docker compose build --pull`. Version pins preserve this experiment;
re-benchmark after updating the runtime or dependencies.

`docker compose down` preserves data. Do not use `down -v` for a database whose
data you want to retain.

## Functional verification

PowerShell, from the repository root:

```powershell
$testPath=(Resolve-Path tests).Path
docker run --rm --network traveler_lab3_backend --mount "type=bind,source=$testPath,target=/tests,readonly" ghcr.io/orange-opensource/hurl:8.0.0 --test --jobs 1 --variable host=http://web:4567 --variable timeout=5000 /tests/crud.hurl /tests/validation.hurl /tests/management.hurl /tests/race-conditions.hurl
docker run --rm --network container:traveler_lab3-web-1 --mount "type=bind,source=$testPath,target=/app/tests,readonly" traveler-api:lab3 node --test tests/concurrency.test.js
```

The concurrency test intentionally uses the API container's network namespace:
its original localhost URL therefore addresses the API without editing the test.

## Reproduce the performance experiment

Only the dedicated disposable `traveler_lab2` database may be reset by the runner.
Set `LAB3_ALLOW_RESET=true` in `.env`, then run `docker compose up -d` to apply it.
The seeder checks both the explicit opt-in and the database name before TRUNCATE.
Install Python 3 and the same k6 2.3.0 used in laboratory 2, then run:

```powershell
python scripts/run-container-performance.py --k6 'C:/path/to/k6.exe'
```

Optional selection: `--tests smoke load stress spike endurance`.
The five scenarios run sequentially. Before each, the dataset is restored to
2000 plans and 6000 locations outside the measured interval. The endurance
profile contains the full 1800-second plateau and two 30-second ramps.
The host k6 process targets the published API port, as it did in laboratory 2.
Raw timestamped JSON, summaries, HTML dashboards, data checks, run metadata and
Docker stats samples (roughly every 7 seconds including command overhead) are
saved together. Exit code 99 records a failed performance threshold; it is not
the same as a server crash or an HTTP error.

Analyze completed runs:

```powershell
python scripts/analyze-performance.py --folder tests/performance-tests/results-docker
python scripts/compare-container-results.py
```

The comparison uses historical native Windows baseline runs and this Docker
Desktop Linux configuration on the same computer. It measures the combined
effect of OS, VM/network/storage paths and configured resource limits. One run
per scenario does not isolate a universal Docker overhead or establish
statistical significance. Docker memory accounting also differs from Windows
process private bytes; report those measurements separately.

## Evidence

`evidence/` contains genuine command outputs and lossless ShareX screenshots.
`evidence/screenshots/*-capture.json` ties each capture to its source file and
hash. The report embeds the original PNG crops without image recompression.

References: https://docs.docker.com/compose/how-tos/startup-order/
and https://hurl.dev/docs/installation.html.
