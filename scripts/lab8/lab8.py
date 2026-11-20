"""Laboratory 8 orchestration: migration of the sharded TravelerAPI (laboratories 6-7) to JSONB documents.
Only the traveler_lab8 Compose project is created or reset.

  python scripts/lab8/lab8.py up              # 4 PostgreSQL, monitoring, API traveler-api:lab7 (relational)
  python scripts/lab8/lab8.py seed            # laboratory 2 dataset (2 000 plans, 6 000 locations) via shard-exec
  python scripts/lab8/lab8.py hurl --tag hurl-before
  python scripts/lab8/lab8.py bench --tag before    # k6 load, key, locations + pg_stat_statements
  python scripts/lab8/lab8.py dump --tag before     # GET of every plan and of 10 list pages, md5
  python scripts/lab8/lab8.py migrate         # maintenance window: stop API, 002 + 100 with 2PC, start traveler-api:lab8
  python scripts/lab8/lab8.py dump --tag after
  python scripts/lab8/lab8.py hurl --tag hurl-after
  python scripts/lab8/lab8.py bench --tag after
  python scripts/lab8/lab8.py explain         # separate database jsonb_bench: sizes, EXPLAIN, WAL per update
  python scripts/lab8/lab8.py contract        # sql/110_drop_legacy.sql on 16 shards
  python scripts/lab8/lab8.py rebalance       # rebalance.js of laboratory 6 moves db_3 and db_7 under load
  python scripts/lab8/lab8.py rollback-check  # dry run of the way back (001 + 190) on 16 shards
"""
import argparse, datetime, hashlib, json, os, re, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'evidence/lab8'; OUT.mkdir(parents=True, exist_ok=True)
RUNTIME = ROOT / '.runtime/lab8'; RUNTIME.mkdir(parents=True, exist_ok=True)
COMPOSE = ['docker', 'compose', '-f', 'docker-compose.lab6.yml', '-f', 'docker-compose.monitoring.yml', '-f', 'docker-compose.lab8.yml']
PROJECT = 'traveler_lab8'
PROM = 'http://127.0.0.1:9090'
K6 = ROOT.parent / '.tools/k6/k6-v2.3.0-windows-amd64/k6.exe'
SERVERS = ['postgres_00', 'postgres_01', 'postgres_02', 'postgres_03']
SHARDS = '0123456789abcdef'
STAGE = RUNTIME / 'api-image.txt'   # which API image the stack runs now (lab7 before, lab8 after the migration)
SEP = '\x1f'
NL = '\n'


def load_env():
    values = {}
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1); values[k] = v
    return values


def api_image():
    return STAGE.read_text().strip() if STAGE.exists() else 'traveler-api:lab7'


def environment(**extra):
    env = os.environ.copy(); env.update(load_env())
    env.update(COMPOSE_PROJECT_NAME=PROJECT, COMPOSE_PROFILES='sharded,monitoring', DOCKER_SUBNET='172.29.80.0/24',
               SHARD_CPUS=os.environ.get('SHARD_CPUS', '0.5'), SHARD_MEMORY=os.environ.get('SHARD_MEMORY', '256M'),
               MAPPING_SOURCE=os.environ.get('MAPPING_SOURCE', 'file'), API_IMAGE=api_image(),
               GRAFANA_PORT=os.environ.get('GRAFANA_PORT', '3001'))  # 3000 is often taken by a local dev server
    env.update(extra)
    return env


def dc(*args, check=True, env=None, **kw):
    return subprocess.run([*COMPOSE, *args], cwd=ROOT, env=env or environment(), text=True, encoding='utf-8', check=check, **kw)


def save(name, value):
    (OUT / name).write_text(value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    return value


def stamp(): return datetime.datetime.now().strftime('%H:%M:%S')
def stamp_ms(): return datetime.datetime.now().strftime('%H:%M:%S.%f')[:-3]
def now_ms(): return int(time.time() * 1000)


def tool(*args, check=True):
    """Run a laboratory 6 CLI tool (shard-exec, rebalance) inside the backend network."""
    r = dc('--profile', 'tools', 'run', '--rm', '-T', 'tools', *args, capture_output=True, check=False)
    text = (r.stdout or '') + '\n'.join(l for l in (r.stderr or '').splitlines() if not l.startswith((' Container', 'Container ')))
    if check and r.returncode: print(text); raise RuntimeError(f'tool failed: {args}')
    return r.returncode, text


def prom(path, **params):
    url = f'{PROM}{path}' + ('?' + urllib.parse.urlencode(params) if params else '')
    with urllib.request.urlopen(url, timeout=10) as r: return json.loads(r.read())


def psql(service, db, sql, stdin=None):
    """Rows of a query as lists (unit separator between columns, so '|' and '||' in SQL text are safe)."""
    admin = load_env()['DB_ADMIN']
    args = ['exec', '-T', service, 'psql', '-X', '-q', '-At', '-v', 'ON_ERROR_STOP=1', '-F', SEP, '-U', admin, '-d', db]
    r = dc(*args, *(['-c', sql] if sql else ['-f', '-']), capture_output=True, input=stdin, check=False)
    if r.returncode: raise RuntimeError(f'psql {service}/{db}: {r.stderr.strip()}')
    return [line.split(SEP) for line in r.stdout.splitlines() if line]


def psql_text(service, db, sql=None, stdin=None, single=False, quiet=False):
    """Plain psql output (aligned) for the report."""
    admin = load_env()['DB_ADMIN']
    args = ['exec', '-T', service, 'psql', '-X', '-v', 'ON_ERROR_STOP=1', '-U', admin, '-d', db]
    if single: args.append('--single-transaction')
    if quiet: args.append('-q')
    r = dc(*args, *(['-c', sql] if sql else ['-f', '-']), capture_output=True, input=stdin, check=False)
    if r.returncode: raise RuntimeError(f'psql {service}/{db}: {r.stderr.strip()}')
    return r.stdout


def server_of(shard): return SERVERS[SHARDS.index(shard) // 4]


# ---------------------------------------------------------------------------
def build():
    subprocess.run(['docker', 'build', '--target', 'runtime', '-t', 'traveler-api:lab8', '.'], cwd=ROOT, check=True)


def up(fresh=True):
    build()
    if fresh:
        dc('down', '-v', '--remove-orphans', capture_output=True, check=False)
        (ROOT / '.runtime/lab6').mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / 'config/mapping.json', ROOT / '.runtime/lab6/mapping.json')
        STAGE.write_text('traveler-api:lab7')
    dc('up', '-d', '--wait', '--no-build', '--remove-orphans')
    for s in SERVERS:
        psql(s, 'postgres', 'CREATE EXTENSION IF NOT EXISTS pg_stat_statements')
    save('compose-ps.txt', dc('ps', '--format', 'table {{.Service}}\t{{.Image}}\t{{.Status}}', capture_output=True).stdout)
    print('READY', PROJECT, 'API', api_image(), flush=True)


def seed():
    _, text = tool('tools/shard-exec.js', '/sql/000_seed_lab2_dataset.sql')
    save('seed-shard-exec.txt', text)
    ids = []
    for i in range(1, 2001):
        h = hashlib.md5(f'lab2-plan-{i}'.encode()).hexdigest()
        ids.append({'id': f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'})
    (ROOT / 'tests/performance-tests/seed.json').write_text(json.dumps(sorted(ids, key=lambda x: x['id'])), encoding='utf-8')
    print('SEEDED', text.strip().splitlines()[-1], flush=True)


def hurl(tag='hurl'):
    r = subprocess.run(['docker', 'run', '--rm', '--network', f'{PROJECT}_backend', '-v', str(ROOT / 'tests') + ':/tests:ro',
                        'ghcr.io/orange-opensource/hurl:8.0.0', '--test', '--color', '--jobs', '1', '--variable', 'host=http://web:4567',
                        '/tests/crud.hurl', '/tests/validation.hurl', '/tests/management.hurl', '/tests/race-conditions.hurl',
                        '/tests/metrics.hurl'], capture_output=True, text=True, encoding='utf-8')
    save(f'{tag}.txt', r.stdout + r.stderr)
    print('HURL', r.returncode, (r.stdout + r.stderr).strip().splitlines()[-6:], flush=True)
    c = subprocess.run(['node', '--test', 'tests/concurrency.test.js'], cwd=ROOT, capture_output=True, text=True, encoding='utf-8',
                       env={**os.environ, 'API_URL': 'http://127.0.0.1:4567'})
    save(f'{tag}-concurrency.txt', c.stdout + c.stderr)
    print('CONCURRENCY', c.returncode, flush=True)
    return r.returncode or c.returncode


# --- pg_stat_statements -----------------------------------------------------
def pgss_reset():
    for s in SERVERS: psql(s, 'postgres', 'SELECT pg_stat_statements_reset()')


def pgss_snapshot():
    """Statements of the API role on the 16 shard databases, merged across servers by query text."""
    app_user, merged = load_env()['APP_USER'], {}
    for srv in SERVERS:
        rows = psql(srv, 'postgres', f"""
          SELECT regexp_replace(s.query, '[[:space:]]+', ' ', 'g'), sum(s.calls), sum(s.total_exec_time), sum(s.rows), sum(s.wal_bytes)
          FROM pg_stat_statements s JOIN pg_database d ON d.oid = s.dbid JOIN pg_roles r ON r.oid = s.userid
          WHERE d.datname ~ '^db_[0-9a-f]$' AND r.rolname = '{app_user}'
          GROUP BY 1""")
        for q, calls, total, nrows, wal in rows:
            m = merged.setdefault(q, {'query': q, 'calls': 0, 'ms': 0.0, 'rows': 0, 'wal': 0})
            m['calls'] += int(calls); m['ms'] += float(total); m['rows'] += int(nrows); m['wal'] += int(float(wal))
    return sorted(merged.values(), key=lambda x: -x['calls'])


def k6(script, tag, **env):
    """k6 run with remote write to Prometheus: k6_* metrics appear in Grafana next to the API metrics."""
    result_dir = f'evidence/lab8/{tag}'; (ROOT / result_dir).mkdir(exist_ok=True)
    e = environment(RESULT_DIR=result_dir, K6_PROMETHEUS_RW_SERVER_URL=f'{PROM}/api/v1/write',
                    K6_PROMETHEUS_RW_TREND_STATS='p(95),avg,max', K6_PROMETHEUS_RW_PUSH_INTERVAL='5s',
                    K6_PROMETHEUS_RW_STALE_MARKERS='true', **env)
    args = [str(K6), 'run', '-o', 'experimental-prometheus-rw', '--tag', f'testid={tag}', f'tests/performance-tests/{script}']
    out = (OUT / f'{tag}-console.txt').open('w', encoding='utf-8')
    out.write(f'$ k6 run -o experimental-prometheus-rw --tag testid={tag} tests/performance-tests/{script}\n'); out.flush()
    proc = subprocess.Popen(args, cwd=ROOT, env=e, stdout=out, stderr=subprocess.STDOUT)
    proc.started_ms = now_ms()
    return proc, out


def finish(proc, out, tag, events):
    code = proc.wait(); out.close()
    save(f'{tag}-events.json', {'exitCode': code, 'startMs': proc.started_ms, 'endMs': now_ms(), 'events': events})
    print('K6', tag, 'exit', code, flush=True)
    return code


def k6_metrics(tag, name):
    m = json.loads((OUT / tag / f'{name}-summary.json').read_text(encoding='utf-8'))['metrics']
    row = {'reqs': m['http_reqs']['values']['count'], 'rps': m['http_reqs']['values']['rate'],
           'avg': m['http_req_duration']['values']['avg'], 'p95': m['http_req_duration']['values']['p(95)'],
           'failed': m['http_req_failed']['values']['rate']}
    for key, metric in m.items():
        g = re.fullmatch(r'http_req_duration\{name:(.+)\}', key)
        if g: row.setdefault('ops', {})[g.group(1)] = {'avg': metric['values']['avg'], 'p95': metric['values']['p(95)']}
    return row


def bench(tag):
    """The same three k6 tests before and after the migration; SQL statements counted by pg_stat_statements."""
    results = {}
    for script, name, env in (('load-test.js', 'load', {}), ('key-test.js', 'key', {}), ('locations-test.js', 'locations', {})):
        test = f'{name}-{tag}'
        pgss_reset(); time.sleep(1)
        proc, out = k6(script, test, API_URL='http://127.0.0.1:4567', **env)
        finish(proc, out, test, [{'start': stamp(), 'api': api_image()}])
        statements = pgss_snapshot()
        save(f'{test}-statements.json', statements)
        row = k6_metrics(test, name)
        sql_calls = sum(s['calls'] for s in statements if s['query'] != 'SELECT $1')
        row.update(api=api_image(), sql=sql_calls, sql_per_request=sql_calls / row['reqs'],
                   sql_ms_per_request=sum(s['ms'] for s in statements if s['query'] != 'SELECT $1') / row['reqs'],
                   wal_per_request=sum(s['wal'] for s in statements) / row['reqs'])
        results[name] = row
        print('BENCH', test, json.dumps({k: v for k, v in row.items() if k != 'ops'}), flush=True)
        time.sleep(15)
    save(f'bench-{tag}.json', results)


# --- API dump: every plan, through the public API -----------------------------
def dump(tag, base='http://127.0.0.1:4567'):
    ids = [p['id'] for p in json.loads((ROOT / 'tests/performance-tests/seed.json').read_text())]
    total, lines = hashlib.md5(), []
    for i, pid in enumerate(ids):
        with urllib.request.urlopen(f'{base}/api/travel-plans/{pid}', timeout=10) as r: body = r.read()
        total.update(body); lines.append(f'{pid} {hashlib.md5(body).hexdigest()}')
        if i == 0: save(f'dump-{tag}-sample.json', json.dumps(json.loads(body), indent=2, ensure_ascii=False))
    for page in range(1, 11):
        with urllib.request.urlopen(f'{base}/api/travel-plans?page={page}&limit=20', timeout=10) as r: body = r.read()
        total.update(body); lines.append(f'list-page-{page} {hashlib.md5(body).hexdigest()}')
    save(f'dump-{tag}.txt', '\n'.join(lines) + '\n')
    result = {'tag': tag, 'api': api_image(), 'responses': len(lines), 'md5': total.hexdigest()}
    save(f'dump-{tag}.json', result)
    print('DUMP', json.dumps(result), flush=True)


class Probe(threading.Thread):
    """GET /health of both API instances every 100 ms: measures the maintenance window."""
    def __init__(self, urls):
        super().__init__(daemon=True); self.urls = urls; self.samples = []; self.running = True

    def run(self):
        while self.running:
            for u in self.urls:
                t = time.time()
                try:
                    with urllib.request.urlopen(u, timeout=0.5) as r: ok = r.status == 200; body = json.loads(r.read())
                except Exception:
                    ok, body = False, {}
                self.samples.append({'url': u, 't': t, 'ok': ok, 'storage': body.get('storage', 'relational' if ok else None)})
            time.sleep(0.1)

    def stop(self):
        self.running = False; self.join()
        out = {}
        for u in self.urls:
            s = [x for x in self.samples if x['url'] == u]
            down = [x for x in s if not x['ok']]
            if down:
                first_down = down[0]['t']
                back = next((x for x in s if x['ok'] and x['t'] > first_down), None)
                last_ok = max((x['t'] for x in s if x['ok'] and x['t'] < first_down), default=first_down)
                out[u] = {'down_from': datetime.datetime.fromtimestamp(first_down).strftime('%H:%M:%S.%f')[:-3],
                          'back_at': back and datetime.datetime.fromtimestamp(back['t']).strftime('%H:%M:%S.%f')[:-3],
                          'unavailable_s': round(((back['t'] if back else s[-1]['t']) - last_ok), 2),
                          'before': s[0]['storage'], 'after': back and back['storage']}
            else:
                out[u] = {'unavailable_s': 0}
        return out


def migrate():
    log = []

    def event(text):
        line = f'{stamp_ms()}  {text}'; log.append(line); print(line, flush=True)

    files = ('/app/db/migrations/002_plan_documents.sql', '/sql/100_migrate_to_jsonb.sql')
    probe = Probe(['http://127.0.0.1:4567/health', 'http://127.0.0.1:4568/health']); probe.start()
    time.sleep(1)
    event(f'dry run of 002 + 100 on 16 shards, the relational API ({api_image()}) keeps serving')
    code, text = tool('tools/shard-exec.js', *files, '--dry-run', check=False)
    save('migrate-dry-run.txt', f'$ node tools/shard-exec.js {" ".join(files)} --dry-run\n{text}')
    event(f'dry run exit {code}')
    if code: raise RuntimeError('dry run failed')
    time.sleep(2)
    event('maintenance window: stop web, web2 (traveler-api:lab7)')
    dc('stop', 'web', 'web2', capture_output=True)
    event('API stopped; shard-exec 002 + 100 with two-phase commit')
    t0 = time.time()
    code, text = tool('tools/shard-exec.js', *files, '--show-prepared', check=False)
    migration_s = time.time() - t0
    save('migrate-shard-exec.txt', f'$ node tools/shard-exec.js {" ".join(files)} --show-prepared\n{text}')
    event(f'shard-exec exit {code} after {migration_s:.1f} s (including the tools container start)')
    if code:
        event('migration rolled back on all shards: start the relational API again')
        dc('start', 'web', 'web2', capture_output=True)
        raise RuntimeError('migration failed')
    STAGE.write_text('traveler-api:lab8')
    event('start web, web2 with traveler-api:lab8 (JSONB)')
    dc('up', '-d', '--wait', '--no-build', 'web', 'web2', capture_output=True)
    event('web, web2 healthy')
    time.sleep(2)
    window = probe.stop()
    for u, w in window.items(): event(f'{u}: unavailable {w["unavailable_s"]} s ({w.get("before")} -> {w.get("after")})')
    save('migrate-window.json', {'migration_s': migration_s, 'probe': window})
    save('migrate-log.txt', '\n'.join(log) + '\n')
    save('compose-ps-after.txt', dc('ps', '--format', 'table {{.Service}}\t{{.Image}}\t{{.Status}}', capture_output=True).stdout)


def rollback_check(tag='rollback-dry-run'):
    files = ('/app/db/migrations/001_schema.sql', '/sql/190_rollback_to_relational.sql')
    code, text = tool('tools/shard-exec.js', *files, '--dry-run', check=False)
    save(f'{tag}.txt', f'$ node tools/shard-exec.js {" ".join(files)} --dry-run\n{text}')
    print('ROLLBACK DRY RUN', code, text.strip().splitlines()[-1], flush=True)


def document_sample(shard='0'):
    """One migrated document as it is stored, and the relational views over it."""
    pid = next(p['id'] for p in json.loads((ROOT / 'tests/performance-tests/seed.json').read_text()) if p['id'].endswith(shard))
    s = server_of(shard)
    head = psql_text(s, f'db_{shard}', f"SELECT id, version, created_at, updated_at, pg_column_size(doc) AS doc_bytes FROM plan_documents WHERE id = '{pid}'")
    body = '\n'.join(r[0] for r in psql(s, f'db_{shard}', f"SELECT jsonb_pretty(doc) FROM plan_documents WHERE id = '{pid}'"))
    save('document-sample.txt', f"$ psql -d db_{shard} -c \"SELECT id, version, created_at, updated_at, pg_column_size(doc) FROM plan_documents WHERE id = '{pid}'\"\n{head}"
                                f"$ psql -d db_{shard} -At -c \"SELECT jsonb_pretty(doc) FROM plan_documents WHERE id = '{pid}'\"\n{body}\n")
    text = psql_text(s, f'db_{shard}', f"SELECT id, name, visit_order, latitude, budget, version FROM locations_view WHERE travel_plan_id = '{pid}'")
    save('document-view.txt', f"$ psql -d db_{shard} -c \"SELECT ... FROM locations_view WHERE travel_plan_id = '{pid}'\"\n{text}")
    text = psql_text(s, f'db_{shard}', '\\d plan_documents')
    save('document-table.txt', f'$ psql -d db_{shard} -c "\\d plan_documents"\n{text}')
    text = psql_text(s, f'db_{shard}', "SELECT name, plans, locations, left(plans_md5, 12) AS plans_md5, migrated_at FROM storage_migrations")
    save('storage-migrations.txt', f'$ psql -d db_{shard} -c "SELECT ... FROM storage_migrations"\n{text}')
    text = psql_text(s, f'db_{shard}', "\\dt")
    save('tables-after.txt', f'$ psql -d db_{shard} -c "\\dt"\n{text}')


def check_demo(shard='0'):
    """The CHECK plan_document_valid rejects broken documents (each change in its own rolled-back transaction)."""
    pid = next(p['id'] for p in json.loads((ROOT / 'tests/performance-tests/seed.json').read_text()) if p['id'].endswith(shard))
    other = '1' if shard != '1' else '2'
    cases = [
        ('two locations with visit_order 1', "jsonb_set(doc, '{locations,1,visit_order}', '1')"),
        (f'location id that ends with {other} (another shard)', f"jsonb_set(doc, '{{locations,0,id}}', to_jsonb(overlay(doc->'locations'->0->>'id' PLACING '{other}' FROM 36)))"),
        ('location without the key "name"', "doc #- '{locations,0,name}'"),
        ('unknown key "owner"', """doc || '{"owner": "someone"}'"""),
        ('currency in lower case', """doc || '{"currency": "eur"}'"""),
        ('latitude 91', "jsonb_set(doc, '{locations,0,latitude}', '91')"),
        ('valid change: notes of the first location', """jsonb_set(doc, '{locations,0,notes}', '"checked"')"""),
    ]
    script = '\\set VERBOSITY terse' + NL + ''.join(f"-- {label}\nBEGIN;\nUPDATE plan_documents SET doc = {expr} WHERE id = '{pid}';\nROLLBACK;\n" for label, expr in cases)
    admin = load_env()['DB_ADMIN']
    r = dc('exec', '-T', server_of(shard), 'sh', '-c', f'psql -X -a -v ON_ERROR_STOP=0 -U {admin} -d db_{shard} 2>&1',
           capture_output=True, input=script, check=False)
    save('check-demo.txt', r.stdout)
    print(r.stdout[-600:], flush=True)


def check_cost(tag):
    """Execution time of one document UPDATE on db_0 with the current CHECK and without it (rolled back)."""
    pid = next(p['id'] for p in json.loads((ROOT / 'tests/performance-tests/seed.json').read_text()) if p['id'].endswith('0'))
    q = f"""UPDATE plan_documents SET doc = jsonb_set(doc, '{{locations,0,notes}}', '"probe"') WHERE id = '{pid}'"""
    lang = psql('postgres_00', 'db_0', "SELECT l.lanname FROM pg_proc p JOIN pg_language l ON l.oid = p.prolang WHERE p.proname = 'plan_document_valid'")[0][0]
    script = (f'BEGIN;\n' + f'EXPLAIN (ANALYZE, COSTS OFF, SUMMARY ON) {q};\n' * 6 + 'ROLLBACK;\n'
              f'BEGIN;\nALTER TABLE plan_documents DROP CONSTRAINT plan_document_valid;\n' +
              f'EXPLAIN (ANALYZE, COSTS OFF, SUMMARY ON) {q};\n' * 6 + 'ROLLBACK;\n')
    out = psql_text('postgres_00', 'db_0', stdin=script)
    times = [float(x) for x in re.findall(r'Execution Time: ([\d.]+) ms', out)]
    with_check, without = times[1:6], times[7:12]  # the first run of each block warms up the session caches
    avg = lambda xs: sum(xs) / len(xs)
    lines = [f'UPDATE of one location in a document (db_0, 3 locations), EXPLAIN ANALYZE, runs 2-6, transaction rolled back',
             f'CHECK plan_document_valid, LANGUAGE {lang:<8}: ' + '  '.join(f'{t:.3f}' for t in with_check) + f'  | avg {avg(with_check):.3f} ms',
             f'without the CHECK (dropped in the transaction):  ' + '  '.join(f'{t:.3f}' for t in without) + f'  | avg {avg(without):.3f} ms',
             f'cost of the CHECK: {avg(with_check) - avg(without):.3f} ms per UPDATE']
    save(f'check-cost-{tag}.json', {'language': lang, 'with_check': with_check, 'without_check': without})
    save(f'check-cost-{tag}.txt', '\n'.join(lines) + '\n')
    print('\n'.join(lines), flush=True)


def shard_sizes(tag):
    rows = []
    for shard in SHARDS:
        r = psql(server_of(shard), f'db_{shard}', """SELECT
          coalesce(pg_total_relation_size(to_regclass('travel_plans')), 0) + coalesce(pg_total_relation_size(to_regclass('locations')), 0),
          coalesce(pg_total_relation_size(to_regclass('legacy_travel_plans')), 0) + coalesce(pg_total_relation_size(to_regclass('legacy_locations')), 0),
          coalesce(pg_total_relation_size(to_regclass('plan_documents')), 0), pg_database_size(current_database())""")[0]
        rows.append({'shard': shard, 'relational': int(r[0]), 'legacy': int(r[1]), 'jsonb': int(r[2]), 'database': int(r[3])})
    save(f'sizes-{tag}.json', rows)
    print('SIZES', tag, {k: sum(r[k] for r in rows) for k in ('relational', 'legacy', 'jsonb', 'database')}, flush=True)


def contract():
    shard_sizes('before-contract')
    code, text = tool('tools/shard-exec.js', '/sql/110_drop_legacy.sql', check=False)
    save('contract-shard-exec.txt', f'$ node tools/shard-exec.js /sql/110_drop_legacy.sql\n{text}')
    shard_sizes('after-contract')
    print('CONTRACT', code, flush=True)


def at(start, seconds):
    while time.time() - start < seconds: time.sleep(0.2)


def rebalance():
    _, before = tool('tools/rebalance.js', 'status'); save('rebalance-status-before.txt', before)
    start = time.time(); events = [{'k6Start': stamp()}]
    proc, out = k6('rebalance-test.js', 'rebalance', DURATION='120s')
    for db, target, second in (('db_3', 'postgres_03', 35), ('db_7', 'postgres_02', 75)):
        at(start, second)
        events.append({'move': db, 'target': target, 'start': stamp(), 'startMs': now_ms()})
        code, text = tool('tools/rebalance.js', 'move', db, target, check=False)
        events[-1].update(end=stamp(), endMs=now_ms(), exitCode=code)
        save(f'rebalance-move-{db}.txt', f'$ node tools/rebalance.js move {db} {target}\n{text}')
        print('MOVED', db, target, code, flush=True)
    finish(proc, out, 'rebalance', events)
    _, after = tool('tools/rebalance.js', 'status'); save('rebalance-status-after.txt', after)


# --- separate database jsonb_bench: sizes, EXPLAIN, WAL -----------------------
BENCH = 'jsonb_bench'


def bench_uuid(text):
    h = hashlib.md5(text.encode()).hexdigest()
    return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'


def bench_location(plan_key, location_key):
    """Location id of 150_bench_dataset.sql: md5 of the location with the last digit of its plan."""
    h = hashlib.md5(location_key.encode()).hexdigest()[:31] + hashlib.md5(plan_key.encode()).hexdigest()[-1]
    return f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'


SIZES_SQL = """SELECT relname AS "table",
  pg_size_pretty(pg_relation_size(c.oid)) AS heap,
  pg_size_pretty(coalesce(pg_total_relation_size(c.reltoastrelid), 0)) AS toast,
  pg_size_pretty(pg_indexes_size(c.oid)) AS indexes,
  pg_size_pretty(pg_total_relation_size(c.oid)) AS total
FROM pg_class c WHERE relkind = 'r' AND relnamespace = 'public'::regnamespace AND relname <> 'storage_migrations'
ORDER BY relname"""


def explain():
    s = 'postgres_00'
    read = lambda p: (ROOT / p).read_text(encoding='utf-8')
    psql(s, 'postgres', f'DROP DATABASE IF EXISTS {BENCH}')
    psql(s, 'postgres', f'CREATE DATABASE {BENCH}')
    t0 = time.time()
    psql_text(s, BENCH, stdin=read('db/migrations/001_schema.sql') + read('sql/150_bench_dataset.sql'), single=True)
    psql(s, BENCH, 'VACUUM ANALYZE')
    load_s = time.time() - t0
    sizes_before = psql_text(s, BENCH, SIZES_SQL)
    counts = psql_text(s, BENCH, 'SELECT (SELECT count(*) FROM travel_plans) AS plans, (SELECT count(*) FROM locations) AS locations')
    t0 = time.time()
    migrated = psql_text(s, BENCH, stdin=read('db/migrations/002_plan_documents.sql') + read('sql/100_migrate_to_jsonb.sql'), single=True, quiet=True)
    migrate_s = time.time() - t0
    psql(s, BENCH, 'VACUUM ANALYZE')
    sizes_after = psql_text(s, BENCH, SIZES_SQL)
    avg = psql_text(s, BENCH, """SELECT round(avg(pg_column_size(doc))) AS avg_doc_bytes,
      round(avg(pg_column_size(doc)) FILTER (WHERE jsonb_array_length(doc->'locations') = 3)) AS doc_3_locations,
      (SELECT round(avg(pg_column_size(t.*))) FROM legacy_travel_plans t) AS plan_row_bytes,
      (SELECT round(avg(pg_column_size(l.*))) FROM legacy_locations l) AS location_row_bytes
      FROM plan_documents""")
    save('bench-sizes.txt', '\n'.join([
        f'$ psql -d {BENCH} -f 001_schema.sql -f sql/150_bench_dataset.sql   # {load_s:.1f} s', counts,
        '$ psql -d jsonb_bench -c "<table sizes>"   # relational tables', sizes_before,
        f'$ psql -d {BENCH} --single-transaction -f 002_plan_documents.sql -f sql/100_migrate_to_jsonb.sql   # {migrate_s:.1f} s', migrated,
        '$ psql -d jsonb_bench -c "<table sizes>"   # after the migration (legacy_* = old tables)', sizes_after,
        '$ psql -d jsonb_bench -c "<average row and document size, bytes>"', avg]))

    plan = bench_uuid('bench-plan-777')
    loc = bench_location('bench-plan-777', 'bench-location-777-2')
    page = ', '.join(f"'{bench_uuid(f'bench-plan-{i}')}'" for i in range(1000, 1020))
    ex = 'EXPLAIN (ANALYZE, BUFFERS, COSTS OFF)'
    queries = {
        'explain-get-relational': [f"{ex} SELECT * FROM legacy_travel_plans WHERE id = '{plan}'",
                                   f"{ex} SELECT * FROM legacy_locations WHERE travel_plan_id = '{plan}' ORDER BY visit_order"],
        'explain-get-jsonb': [f"{ex} SELECT id, doc, version, created_at, updated_at FROM plan_documents WHERE id = '{plan}'"],
        'explain-location-relational': [f"{ex} SELECT travel_plan_id FROM legacy_locations WHERE id = '{loc}'"],
        'explain-location-gin': [f"""{ex} SELECT id FROM plan_documents WHERE doc->'locations' @> '[{{"id": "{loc}"}}]'"""],
        'explain-location-seqscan': ['SET enable_bitmapscan = off; SET enable_indexscan = off;\n' +
                                     f"""{ex} SELECT id FROM plan_documents WHERE doc->'locations' @> '[{{"id": "{loc}"}}]'"""],
        'explain-list-relational': [f"""{ex} SELECT p.*, COUNT(l.id)::integer AS location_count
FROM legacy_travel_plans p LEFT JOIN legacy_locations l ON l.travel_plan_id = p.id
WHERE p.id = ANY(ARRAY[{page}]::uuid[]) GROUP BY p.id"""],
        'explain-list-jsonb': [f"""{ex} SELECT id, doc - 'locations' AS doc, version, created_at, updated_at,
       jsonb_array_length(doc->'locations') AS location_count
FROM plan_documents WHERE id = ANY(ARRAY[{page}]::uuid[])"""],
    }
    for name, statements in queries.items():
        parts = []
        for q in statements:
            psql_text(s, BENCH, q)  # warm-up: the measured run has a warm cache
            shown = [f'{BENCH}=# {line}' if line.startswith(('SET', 'EXPLAIN')) else line for line in q.split(NL)]
            parts.append(NL.join(shown) + ';' + NL)
            parts.append(psql_text(s, BENCH, q))
        save(f'{name}.txt', ''.join(parts))

    # WAL written by one location update, relational row vs whole document.
    wal = []
    cases = [(3, 'bench-plan-777', 'bench-location-777-1')] + [(n, f'bench-big-{n}', f'bench-big-{n}-1') for n in (20, 100, 300)]
    for n, plan_key, loc_key in cases:
        pid, lid = bench_uuid(plan_key), bench_location(plan_key, loc_key)
        rel = f"UPDATE legacy_locations SET notes = 'WAL test', version = version + 1 WHERE id = '{lid}'"
        doc = (f"UPDATE plan_documents SET doc = jsonb_set(doc, '{{locations,0}}', "
               f"(doc->'locations'->0) || jsonb_build_object('notes', 'WAL test', 'version', (doc->'locations'->0->>'version')::int + 1)) "
               f"WHERE id = '{pid}'")
        row = {'locations': n, 'doc_bytes': int(psql(s, BENCH, f"SELECT pg_column_size(doc) FROM plan_documents WHERE id = '{pid}'")[0][0])}
        for kind, q in (('relational', rel), ('jsonb', doc)):
            for attempt in range(4):  # the first run may write full-page images after a checkpoint
                out = psql_text(s, BENCH, f'BEGIN; EXPLAIN (ANALYZE, WAL, COSTS OFF) {q}; ROLLBACK;')
            m = re.search(r'WAL: records=(\d+)(?: fpi=(\d+))? bytes=(\d+)', out)
            t = re.search(r'Execution Time: ([\d.]+) ms', out)
            row[kind] = {'records': int(m.group(1)), 'fpi': int(m.group(2) or 0), 'bytes': int(m.group(3)), 'ms': float(t.group(1))}
            if n == 100: save(f'wal-explain-{kind}.txt', f'{BENCH}=# BEGIN; EXPLAIN (ANALYZE, WAL, COSTS OFF) {q}; ROLLBACK;\n{out}')
        wal.append(row)
        print('WAL', json.dumps(row), flush=True)
    save('wal.json', wal)
    lines = ['locations | document, B | relational: WAL records / bytes / ms | jsonb: WAL records / bytes / ms | WAL ratio',
             '----------+-------------+--------------------------------------+---------------------------------+----------']
    for r in wal:
        a, b = r['relational'], r['jsonb']
        lines.append(f"{r['locations']:>9} | {r['doc_bytes']:>11} | {a['records']:>6} / {a['bytes']:>7} / {a['ms']:>7.3f} | "
                     f"{b['records']:>6} / {b['bytes']:>7} / {b['ms']:>7.3f} | {b['bytes'] / a['bytes']:>7.1f}x")
    save('wal.txt', '\n'.join(lines) + '\n')
    psql(s, 'postgres', f'DROP DATABASE {BENCH}')
    print('EXPLAIN done', flush=True)


def snapshot(tag='snapshot'):
    targets = prom('/api/v1/targets')['data']['activeTargets']
    save(f'{tag}-targets.json', [{'job': t['labels']['job'], 'instance': t['labels']['instance'], 'health': t['health']} for t in targets])
    print('TARGETS', {t['labels']['instance']: t['health'] for t in targets}, flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action'); p.add_argument('--keep', action='store_true'); p.add_argument('--tag', default='')
    a = p.parse_args()
    actions = {'build': build, 'up': lambda: up(not a.keep), 'seed': seed, 'hurl': lambda: sys.exit(hurl(a.tag or 'hurl')),
               'bench': lambda: bench(a.tag), 'dump': lambda: dump(a.tag), 'migrate': migrate, 'rollback-check': lambda: rollback_check(a.tag or 'rollback-dry-run'),
               'document': document_sample, 'check-demo': check_demo, 'check-cost': lambda: check_cost(a.tag), 'sizes': lambda: shard_sizes(a.tag), 'contract': contract, 'rebalance': rebalance,
               'explain': explain, 'snapshot': lambda: snapshot(a.tag or 'snapshot'), 'down': lambda: dc('down'), 'stop': lambda: dc('stop')}
    if a.action not in actions: raise SystemExit(f'unknown action {a.action}')
    actions[a.action]()
