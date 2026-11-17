"""Laboratory 7 orchestration: sharded TravelerAPI of laboratory 6 + Prometheus/Grafana.
Only the traveler_lab7 Compose project is created or reset.

  python scripts/lab7/bootstrap-env.py
  python scripts/lab7/lab7.py up          # 4 PostgreSQL, 2 API, exporters, Prometheus, Grafana
  python scripts/lab7/lab7.py seed        # laboratory 2 dataset (2 000 plans) via shard-exec
  python scripts/lab7/lab7.py load        # k6 Load of laboratory 2, metrics pushed to Prometheus
  python scripts/lab7/lab7.py rebalance   # move db_3 and db_7 under load (laboratory 6 tool)
  python scripts/lab7/lab7.py failure     # stop postgres_02 for 45 s under load, alerts fire
  python scripts/lab7/lab7.py hotspot     # load only shard 5, ShardHotspot alert
  python scripts/lab7/lab7.py snapshot    # targets, rules, alerts, metric samples -> evidence/lab7
"""
import argparse, datetime, hashlib, json, os, shutil, subprocess, sys, threading, time, urllib.parse, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))
OUT = ROOT / 'evidence/lab7'; OUT.mkdir(parents=True, exist_ok=True)
COMPOSE = ['docker', 'compose', '-f', 'docker-compose.lab6.yml', '-f', 'docker-compose.monitoring.yml']
PROJECT = 'traveler_lab7'
PROM = 'http://127.0.0.1:9090'
K6 = ROOT.parent / '.tools/k6/k6-v2.3.0-windows-amd64/k6.exe'


def load_env():
    values = {}
    for line in (ROOT / '.env').read_text(encoding='utf-8').splitlines():
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1); values[k] = v
    return values


def environment(**extra):
    env = os.environ.copy(); env.update(load_env())
    env.update(COMPOSE_PROJECT_NAME=PROJECT, COMPOSE_PROFILES='sharded,monitoring', DOCKER_SUBNET='172.29.70.0/24',
               SHARD_CPUS=os.environ.get('SHARD_CPUS', '0.5'), SHARD_MEMORY=os.environ.get('SHARD_MEMORY', '256M'),
               MAPPING_SOURCE=os.environ.get('MAPPING_SOURCE', 'file'))
    env.update(extra)
    return env


def dc(*args, check=True, **kw):
    return subprocess.run([*COMPOSE, *args], cwd=ROOT, env=environment(), text=True, encoding='utf-8', check=check, **kw)


def save(name, value):
    (OUT / name).write_text(value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')
    return value


def stamp(): return datetime.datetime.now().strftime('%H:%M:%S')
def now_ms(): return int(time.time() * 1000)


def tool(*args, check=True):
    """Run a laboratory 6 CLI tool (shard-exec, rebalance) inside the backend network."""
    r = dc('--profile', 'tools', 'run', '--rm', '-T', 'tools', *args, capture_output=True, check=False)
    text = (r.stdout or '') + '\n'.join(l for l in (r.stderr or '').splitlines() if not l.startswith(' Container'))
    if check and r.returncode: print(text); raise RuntimeError(f'tool failed: {args}')
    return r.returncode, text


def prom(path, **params):
    url = f'{PROM}{path}' + ('?' + urllib.parse.urlencode(params) if params else '')
    with urllib.request.urlopen(url, timeout=10) as r: return json.loads(r.read())


def promql(expr):
    return prom('/api/v1/query', query=expr)['data']['result']


def up(fresh=True):
    if fresh:
        dc('down', '-v', '--remove-orphans', capture_output=True, check=False)
        (ROOT / '.runtime/lab6').mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / 'config/mapping.json', ROOT / '.runtime/lab6/mapping.json')
    dc('up', '-d', '--wait', '--build', '--remove-orphans')
    save('compose-ps.txt', dc('ps', '--format', 'table {{.Service}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}', capture_output=True).stdout)
    print('READY', PROJECT, flush=True)


def reset_data():
    """Fresh PostgreSQL volumes and initial mapping; Prometheus and Grafana keep their history."""
    nodes = ['postgres_00', 'postgres_01', 'postgres_02', 'postgres_03']
    dc('rm', '-sf', 'web', 'web2', 'pg_exporter_00', 'pg_exporter_01', 'pg_exporter_02', 'pg_exporter_03', *nodes, capture_output=True)
    for n in ('00', '01', '02', '03'):
        subprocess.run(['docker', 'volume', 'rm', f'{PROJECT}_pg{n}_data'], capture_output=True)
    shutil.copy(ROOT / 'config/mapping.json', ROOT / '.runtime/lab6/mapping.json')
    dc('up', '-d', '--wait')
    print('RESET', PROJECT, 'shards and API recreated, monitoring history kept', flush=True)


def seed():
    _, text = tool('tools/shard-exec.js', '/sql/000_seed_lab2_dataset.sql')
    save('seed-shard-exec.txt', text)
    ids = []
    for i in range(1, 2001):
        h = hashlib.md5(f'lab2-plan-{i}'.encode()).hexdigest()
        ids.append({'id': f'{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}'})
    (ROOT / 'tests/performance-tests/seed.json').write_text(json.dumps(sorted(ids, key=lambda x: x['id'])), encoding='utf-8')
    print('SEEDED', text.strip().splitlines()[-1], flush=True)


def k6(script, tag, **env):
    """k6 run with remote write to Prometheus: k6_* metrics appear in Grafana next to the API metrics."""
    result_dir = f'evidence/lab7/{tag}'; (ROOT / result_dir).mkdir(exist_ok=True)
    e = environment(RESULT_DIR=result_dir, K6_PROMETHEUS_RW_SERVER_URL=f'{PROM}/api/v1/write',
                    K6_PROMETHEUS_RW_TREND_STATS='p(95),avg,max', K6_PROMETHEUS_RW_PUSH_INTERVAL='5s',
                    K6_PROMETHEUS_RW_STALE_MARKERS='true', **env)  # series end with the test
    args = [str(K6), 'run', '-o', 'experimental-prometheus-rw', '--tag', f'testid={tag}', f'tests/performance-tests/{script}']
    out = (OUT / f'{tag}-console.txt').open('w', encoding='utf-8')
    out.write(f'$ k6 run -o experimental-prometheus-rw --tag testid={tag} tests/performance-tests/{script}' + chr(10)); out.flush()
    proc = subprocess.Popen(args, cwd=ROOT, env=e, stdout=out, stderr=subprocess.STDOUT)
    proc.started_ms = now_ms()
    return proc, out


def finish(proc, out, tag, events):
    code = proc.wait(); out.close()
    save(f'{tag}-events.json', {'exitCode': code, 'startMs': proc.started_ms, 'endMs': now_ms(), 'events': events})
    print('K6', tag, 'exit', code, flush=True)


def at(start, seconds):
    while time.time() - start < seconds: time.sleep(0.2)


def psql(service, db, sql):
    admin = load_env()['DB_ADMIN']
    return dc('exec', '-T', service, 'psql', '-X', '-At', '-F', ' | ', '-U', admin, '-d', db, '-c', sql, capture_output=True).stdout.strip()


def created_at():
    """Seed rows of one shard share created_at (one transaction per shard); list pages read the newest shards."""
    rows = []
    for i, s in enumerate('0123456789abcdef'):
        server = f'postgres_0{i // 4}'
        out = psql(server, f'db_{s}', "SELECT count(*), count(DISTINCT created_at), to_char(max(created_at) AT TIME ZONE 'UTC', "
                   "'HH24:MI:SS.US') FROM travel_plans")
        n, distinct, at_ = out.split(' | ')
        rows.append({'shard': s, 'server': server, 'plans': int(n), 'distinct': int(distinct), 'createdAt': at_})
    rows.sort(key=lambda r: r['createdAt'])
    save('created-at.json', rows)
    header = 'shard | server      | plans | distinct created_at | created_at (UTC)'
    body = [f"db_{r['shard']}  | {r['server']} | {r['plans']:>5} | {r['distinct']:>19} | {r['createdAt']}" for r in rows]
    save('created-at.txt', chr(10).join([header, *body]) + chr(10))


def load():
    seed()
    created_at()
    proc, out = k6('load-test.js', 'load', API_URL='http://127.0.0.1:4567')
    finish(proc, out, 'load', [{'start': stamp()}])


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


def live_shots(tag, minutes=5):
    """Browser screenshots while the situation is still live (alerts are firing)."""
    from browser_shots import Browser
    b = Browser()
    try:
        b.alerts(f'p-alerts-{tag}')
        b.grafana('traveler-api', f'g-api-{tag}-live', f'now-{minutes}m', 'now')
        b.grafana('traveler-postgres', f'g-pg-{tag}-live', f'now-{minutes}m', 'now')
    finally:
        b.close()


def failure(server='postgres_02'):
    start = time.time(); events = [{'k6Start': stamp()}]
    proc, out = k6('shards-test.js', 'failure', MODE='uniform', DURATION='150s', VUS='40')
    at(start, 35)
    events.append({'stop': server, 'at': stamp(), 'ms': now_ms()}); dc('stop', server, capture_output=True); print('STOPPED', server, stamp(), flush=True)
    firing = []
    while time.time() - start < 85:
        time.sleep(5)
        alerts = prom('/api/v1/alerts')['data']['alerts']
        firing = [a for a in alerts if a['state'] == 'firing']
        print(stamp(), 'alerts:', sorted({a['labels']['alertname'] for a in firing}), flush=True)
    save('failure-alerts-firing.json', alerts)
    live_shots('failure', 3)
    save('failure-api-errors.json', promql('sum by (shard, server, code) (increase(db_errors_total[1m]))'))
    events.append({'start': server, 'at': stamp(), 'ms': now_ms()}); dc('start', server, capture_output=True); print('STARTED', server, stamp(), flush=True)
    finish(proc, out, 'failure', events)
    save('failure-alerts-after.json', prom('/api/v1/alerts')['data']['alerts'])


def hotspot(shard='5'):
    start = time.time()
    proc, out = k6('shards-test.js', 'hotspot', MODE='hotspot', HOT_SHARD=shard, DURATION='120s', VUS='30')
    at(start, 90)
    save('hotspot-alerts-firing.json', prom('/api/v1/alerts')['data']['alerts'])
    live_shots('hotspot', 3)
    finish(proc, out, 'hotspot', [{'shard': shard, 'start': stamp()}])
    save('hotspot-alerts.json', prom('/api/v1/alerts')['data']['alerts'])


def overhead(runs=3):
    """key-test.js (200 VU, 45 s, single-shard reads) with and without the instrumentation and Prometheus."""
    results = {}
    for mode in ('on', 'off', 'on', 'off', 'on', 'off')[:runs * 2]:
        subprocess.run([*COMPOSE, 'up', '-d', '--wait', 'web', 'web2'], cwd=ROOT, env=environment(METRICS=mode),
                       capture_output=True, check=True)
        dc('stop' if mode == 'off' else 'start', 'prometheus', capture_output=True)
        time.sleep(5)
        tag = f'overhead-{mode}-{len(results.get(mode, [])) + 1}'
        e = environment(RESULT_DIR=f'evidence/lab7/{tag}', API_URL='http://127.0.0.1:4567')
        (ROOT / e['RESULT_DIR']).mkdir(exist_ok=True)
        with (OUT / f'{tag}-console.txt').open('w', encoding='utf-8') as out:
            subprocess.run([str(K6), 'run', 'tests/performance-tests/key-test.js'], cwd=ROOT, env=e, stdout=out, stderr=subprocess.STDOUT)
        m = json.loads((ROOT / e['RESULT_DIR'] / 'key-summary.json').read_text())['metrics']
        row = {'rps': m['http_reqs']['values']['rate'], 'p95': m['http_req_duration']['values']['p(95)'],
               'avg': m['http_req_duration']['values']['avg'], 'failed': m['http_req_failed']['values']['rate']}
        results.setdefault(mode, []).append(row)
        print('OVERHEAD', tag, json.dumps(row), flush=True)
    subprocess.run([*COMPOSE, 'up', '-d', '--wait', 'web', 'web2', 'prometheus'], cwd=ROOT, env=environment(METRICS='on'),
                   capture_output=True, check=True)
    save('overhead.json', results)


def snapshot(tag='snapshot'):
    targets = prom('/api/v1/targets')['data']['activeTargets']
    save(f'{tag}-targets.json', [{'job': t['labels']['job'], 'instance': t['labels']['instance'], 'health': t['health'],
                                  'lastScrapeDuration': t['lastScrapeDuration'], 'labels': t['labels']} for t in targets])
    save(f'{tag}-rules.json', prom('/api/v1/rules')['data'])
    save(f'{tag}-alerts.json', prom('/api/v1/alerts')['data']['alerts'])
    names = prom('/api/v1/label/__name__/values')['data']
    save(f'{tag}-metric-names.json', names)
    print('TARGETS', {t['labels']['instance']: t['health'] for t in targets}, 'METRICS', len(names), flush=True)


def hurl(tag='hurl'):
    r = subprocess.run(['docker', 'run', '--rm', '--network', f'{PROJECT}_backend', '-v', str(ROOT / 'tests') + ':/tests:ro',
                        'ghcr.io/orange-opensource/hurl:8.0.0', '--test', '--color', '--jobs', '1', '--variable', 'host=http://web:4567',
                        '/tests/crud.hurl', '/tests/validation.hurl', '/tests/management.hurl', '/tests/race-conditions.hurl',
                        '/tests/metrics.hurl'], capture_output=True, text=True, encoding='utf-8')
    save(f'{tag}.txt', r.stdout + r.stderr)
    print('HURL', r.returncode, (r.stdout + r.stderr).strip().splitlines()[-6:], flush=True)
    return r.returncode


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action'); p.add_argument('--keep', action='store_true'); p.add_argument('--tag', default='snapshot')
    a = p.parse_args()
    actions = {'up': lambda: up(not a.keep), 'reset-data': reset_data, 'seed': seed, 'load': load, 'rebalance': rebalance, 'failure': failure,
               'hotspot': hotspot, 'overhead': overhead, 'created-at': created_at, 'snapshot': lambda: snapshot(a.tag), 'hurl': lambda: sys.exit(hurl(a.tag if a.tag != 'snapshot' else 'hurl')),
               'down': lambda: dc('down'), 'stop': lambda: dc('stop')}
    if a.action not in actions: raise SystemExit(f'unknown action {a.action}')
    actions[a.action]()
