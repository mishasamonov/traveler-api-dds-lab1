# TravelerAPI performance baseline

The API implementation and schema are unchanged from lab 1. Lab 2 lives on
`lab2-performance`. Run the API and a real PostgreSQL server on the same host,
without Docker or a virtual machine. Use an isolated database named `traveler_lab2`.

## Run

1. Install Node.js, native PostgreSQL 16, and Grafana k6 2.3.0.
2. Set `DATABASE_URL` to the disposable database and run `npm ci --omit=dev`.
3. Run `node scripts/init-db.js` and `npm start` in a separate process.
4. PowerShell: `./scripts/run-performance.ps1 -Test smoke -K6 /path/to/k6.exe`.
5. Repeat with `load`, `stress`, `spike`, `endurance` in that order. Do not run
   performance tests concurrently. Endurance includes a full 30 minute plateau.

The runner resets only `traveler_lab2` to 2000 plans and 6000 locations before
each run. `seed-performance.cjs` refuses any other database name. Never point
this suite at production. Override `API_URL` for another local port.

## Workload and interpretation

Each VU owns a different seeded plan (up to 2000 VUs). A normal journey contains
8 reads and 2 optimistic updates, with five 100 ms think times. Every tenth
journey adds create-plan, add-location and cascade-delete requests. This avoids
unbounded dataset growth. The smoke test separately verifies create/read/update/
delete, version increments, expected 409 and 404 responses, and safe retries.
Expected 409/404 responses are successful only in those explicit smoke checks.
Any 409 in the measured workload is unexpected and counts as a failure.

The SLO is p95 < 500 ms and unexpected HTTP failures < 1%. Degradation is the
first stable stress plateau that misses either SLO. An operational breaking point
is the first plateau with p95 >= 2000 ms or failures >= 1%; a complete process
crash is reported separately. Capacity is a tested bound for this workload and
machine, not a universal maximum. This is a closed workload: slow responses
reduce the achieved request rate. k6, the API, and PostgreSQL share host resources.

`*-summary.json` is the k6 aggregate; `*-console.txt` is actual stdout;
`*-raw.json.gz` holds timestamped samples; `*-resources.csv` records cumulative
process CPU seconds and memory every five seconds. `*-dashboard.html` is the
unmodified self-contained k6 web dashboard export. Ramp periods and setup are
excluded from plateau comparisons. CI is a smoke regression check only; its
performance numbers are not comparable to this local native baseline.

## Instructor material

Adapted from https://github.com/potapuff/SumDU.DDS.25F.lab2 at
`767c73d99aaa8e353e501b1e8b2a2fb5cb9a622c` (MIT).
Original smoke script, endpoints and client are retained in `instructor/` with
their license. The data generator is copied with a local replacement for the
two random helper functions, so k6 does not download remote modules at runtime.
The adapted client checks the expected status on every call and passes the
latest location `version` when updating. It never changes the API to make a
performance test pass.

Native Windows restart instructions are in `docs/lab2-native-windows.md`.
Optional Python dependencies for plots and the Word report are listed in
`requirements-report.txt`. Run `scripts/analyze-performance.py --plot` after
measurement has finished, followed by `scripts/verify-performance-results.py`.
The analyzer compares stable plateaus using request completion timestamps and
excludes five seconds at each edge; settled recovery also excludes the configured
30-second graceful drain. Recovery time requires three consecutive
five-second windows meeting the SLO. Full raw samples are included in the local
result archive; Git contains summaries, analyses, charts and original dashboards.

## Screenshot evidence

`screenshots/` contains nine native ShareX PNG captures of the saved k6 logs
and the successful functional CI log displayed in Windows Notepad. These were
captured after execution; they are not live terminal captures. Only the log
body was cropped, without resampling or editing its contents. Matching
`*-capture.json` files identify each source log and its SHA-256 digest.
The Word report places all nine images next to the corresponding test text,
with short captions and no appendices. It keeps only the repository link and
two main commit links. Source filenames and capture details are retained here
in the repository metadata.

`results/ci-functional-proof.json` records three successful runs on commit
`3b59534`: the functional suite and both k6 smoke triggers. The functional
runner is pinned to Ubuntu 24.04 with `libxml2` installed for Hurl. Its original
test step is preserved in `results/ci-functional-test-step.txt` (56 Hurl
requests and three concurrency tests passed). Old failed runs remain in GitHub
history; current PR checks must be assessed on its latest commit.
